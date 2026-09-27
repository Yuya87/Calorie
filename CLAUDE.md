# 1. システム・技術スタック & アーキテクチャ概要
- **フロントエンド / サービスレイヤー**: Streamlit (Python)
- **データベース**: Google Cloud Firestore (NoSQL / gcp_service_account 経由で接続)
- **AI LLM SDK**: `google-genai` (使用モデル: `gemini-3.6-flash` / JSONレスポンスモード利用)
- **クラウドインフラ / デプロイ先**: Streamlit Community Cloud (環境変数: `st.secrets` で管理)
- **データビジュアライゼーション**: Plotly Express, Pandas

### 📂 ディレクトリ・ファイル構成（責任分離: SoC）
1. `firestore_db.py`: Firestoreの初期化およびデータ操作（CRUD）を集約したデータベースレイヤー
2. `ai_services.py`: Gemini 3.6 Flashを使った解析・フィードバック生成ロジックを集約したAIサービスレイヤー
   - `analyze_meal_text` / `analyze_exercise_text`: テキストから1件分の栄養素・運動データを推定（JSONレスポンス、失敗時は `None`）
   - `generate_meal_feedback`: 食事保存直後のウィットに富んだコメント（当日＋直近3日の食事と目標値を参照）
   - `generate_journal_feedback`: 振り返り＋当日の習慣・食事・運動を踏まえたフィードバック
3. `app.py`: Streamlitの画面構築、タブレイアウト、セッション状態管理を担うメインUIレイヤー

---

# 2. Firestore データ構造（コレクション設計）

1. `meals` (食事ログ)
   - **ドキュメントID**: 自動生成
   - **フィールド**:
     - `date` (str): YYYY-MM-DD
     - `meal_type` (str): 「朝食」「昼食」「夕食」「間食」「不明」
     - `food_name` (str): 品目名
     - `calories` (float): カロリー (kcal)
     - `protein` (float): タンパク質 (g)
     - `fat` (float): 脂質 (g)
     - `carbs` (float): 炭水化物 (g)
     - `alcohol_g` (float): アルコール量 (g)
     - `is_eating_out` (bool): 外食フラグ
     - `restaurant_name` (str): 店名・場所
     - `dining_partners` (str): 同行者
     - `eating_out_comment` (str): 外食メモ・評価
     - `created_at` (TIMESTAMP): SERVER_TIMESTAMP

2. `exercises` (運動ログ)
   - **ドキュメントID**: 自動生成
   - **フィールド**:
     - `date` (str): YYYY-MM-DD
     - `exercise_name` (str): 種目名（例: 傾斜ウォーキング）
     - `duration_min` (float): 実施時間 (分)
     - `burned_calories` (float): 消費カロリー (kcal)
     - `created_at` (TIMESTAMP): SERVER_TIMESTAMP

3. `daily_habits` (日次習慣化チェックイン)
   - **ドキュメントID**: `YYYY-MM-DD` (日付キー)
   - **フィールド**:
     - `date` (str): YYYY-MM-DD
     - `gym` (str): 運動ステータス ("目標達成", "一応やった", "未実施", "未記録")
     - `english` (str): 英語学習ステータス ("目標達成", "一応やった", "未実施", "未記録")
     - `rest_day` (str): 休肝日ステータス ("目標達成", "一応やった", "未実施", "未記録")
       ※ 画面上は「未実施」を「飲酒」と表示する（保存値は「未実施」のまま。過去データとの互換性のため変更しないこと）
     - `memo` (str): 習慣メモ
     - `updated_at` (TIMESTAMP): SERVER_TIMESTAMP

4. `body_composition` (体組成データ)
   - **ドキュメントID**: `YYYY-MM-DD` (日付キー)
   - **フィールド**:
     - `date` (str): YYYY-MM-DD
     - `weight` (float): 体重 (kg)
     - `body_fat` (float): 体脂肪率 (%)
     - `muscle_mass` (float): 骨格筋量 (kg)
     - `bmr` (float): 基礎代謝 (kcal)
     - `updated_at` (TIMESTAMP): SERVER_TIMESTAMP

5. `journals` (ジャーナリング・振り返り)
   - **ドキュメントID**: `YYYY-MM-DD` (日付キー)
   - **フィールド**:
     - `date` (str): YYYY-MM-DD
     - `note` (str): 振り返り・体調・気づき
     - `ai_feedback` (str): AIからのフィードバックコメント
     - `updated_at` (TIMESTAMP): SERVER_TIMESTAMP

6. `user_goals` (目標設定履歴)
   - **ドキュメントID**: 自動生成（降順取得で最新1件を利用）
   - **フィールド**:
     - `target_cal` (float): 目標カロリー
     - `target_p` (float): 目標タンパク質 (g)
     - `target_f` (float): 目標脂質 (g)
     - `target_c` (float): 目標炭水化物 (g)
     - `updated_at` (TIMESTAMP): SERVER_TIMESTAMP

7. `user_rules` (カスタム栄養・辞書ルール)
   - **ドキュメントID**: 自動生成
   - **フィールド**:
     - `title` (str): 単語・料理名
     - `detail` (str): 計算ルール・仕様プロンプト
     - `created_at` (TIMESTAMP): SERVER_TIMESTAMP

---

# 3. アプリケーションUI構成（Streamlit タブ構成）

- **サイドバー**: 目標マクロ設定（カロリー・PFC）の変更・保存
- **TAB 1: 📝 本日のデータ入力** (メイン画面)
  - 記録対象日の選択 (日付＋曜日表示。`key="selected_date"` で session_state と連動)
  - 🏋️ 1. 習慣化チェックイン (運動・英語・休肝日ラジオボタン & メモ入力。記録対象日を変えると登録済みデータを読み込んで選択表示。休肝日は「未記録／目標達成／一応やった／飲酒」)
  - 🥗 2. 食事ログの入力 (単語辞書登録・確認、食事種別の横並びラジオボタン（初期値「不明」）、AIテキスト解析入力、外食詳細フラグ・コメント入力、保存後に当日＋直近3日の食事を踏まえたAIフィードバック「🍽️ コーチからのひとこと」を表示 ※Firestoreには保存しない)
  - 🏃 3. 運動ログの入力 (傾斜ウォーキング 1タップ入力、AIテキスト解析入力)
  - 📖 4. 本日のジャーナリング（振り返り入力 ＆ Geminiフィードバック表示）
  - ⚙️ 5. 体組成データの入力 (オムロン/タニタ等のCSV一括アップロード機能)
- **TAB 2: 📊 日次サマリー＆KPI**
  - 任意の日付選択機能
  - カロリー/PFC/消費カロリーの達成度Metric表示
  - 選択日の習慣達成ステータス表示（休肝日の「未実施」は「飲酒」と表示）
  - 食事明細のソート表示（朝→昼→夕→間食順、各行にカロリーとPFCを表示）およびインライン編集ポップオーバー・削除機能
  - 運動明細の表示（食事明細の下。種目名・実施時間・消費カロリー）およびインライン編集ポップオーバー・削除機能
- **TAB 3: 📈 習慣＆体組成の分析**
  - 過去30日間の習慣達成ヒートマップ（Plotly imshow。正方形セル＋縦横の隙間、x軸はカテゴリ軸・MM/DD表記）
    - 配色: 目標達成=濃い青 `#1d4ed8` / 一応やった=薄い青 `#93c5fd` / 未実施(飲酒)=グレー `#9ca3af` / 未記録=薄いグレー `#ebedf0`
  - 体組成データの推移グラフ（登録データ全期間。体脂肪率・体脂肪量・骨格筋量 ※体重は非表示）
- **TAB 4: 📊 過去1週間の推移**
  - 過去7日間の合計摂取カロリー推移（目標線付き）
  - PFC（タンパク質・脂質・炭水化物）それぞれ別の棒グラフで過去7日間摂取量推移（横並び3グラフ、各目標線付き）
- **TAB 5: ⚙️ 設定**
  - アプリ・目標設定の案内

### 🛠️ 実装上の注意
- 日付ごとに初期値が変わる入力ウィジェット（習慣ラジオ・メモ等）は、`key` に日付を含める（例: `key=f"habit_gym_{date_str}"`）。固定keyだと日付を変えても前の選択が残る。
- `st.date_input` に `value=st.session_state[...]` を渡して同じ session_state を上書きする書き方は、2回目以降の変更が無視されるため使わない（`key` で連動させる）。
- 登録成功後の入力欄クリアは、保存時にフラグ（例: `clear_meal_inputs`）を立てて `st.rerun()` し、次回描画でウィジェット生成前に該当keyへ初期値を**代入**する（`reset_inputs`）。keyを削除するだけではサーバー側の値は消えても画面上に前の入力が残る。生成後のkeyへの代入はエラーになる。初期値は session_state で与え、ウィジェット側には `value`/`index` を渡さない。
- `st.file_uploader` は session_state でクリアできないため、key にバージョン番号を含めて保存成功時に番号を上げる。
- スマホ表示を考慮し、ラジオボタンは `horizontal=True` で横並びにする。タイトルは `st.title` ではなくCSSで縮小した見出しを使い、上部余白も詰めている。セクション見出し（h2〜h4）もCSSで縮小している。横並びラジオはCSSで選択肢間・丸と文字の間隔を詰め、スマホ幅でも1行に収めている。

---

# 4. 英語学習アプリ（English Growth Log）

Body Make アプリとは別の Streamlit アプリ（起動ファイル `english_app.py`）。同じリポジトリ・同じ Firestore / Gemini の設定を流用する。
Streamlit Community Cloud では別アプリとしてデプロイし、Secrets も個別に設定する（`pages/` フォルダは作らない。作ると `app.py` のページとして自動で取り込まれる）。

### 📂 ファイル構成
1. `english_db.py`: 英語アプリ用の Firestore CRUD と Cloud Storage（音声ファイル）操作。Firestore クライアントは `firestore_db.db` を流用
2. `english_ai.py`: 音声の WAV 変換（`imageio-ffmpeg`）と Gemini による1分スピーチ分析。Gemini クライアントは `ai_services.ai_client` を流用
3. `english_app.py`: 英語アプリの画面
- Body Make 側のファイル（`app.py`, `firestore_db.py`, `ai_services.py`）の変更は英語アプリにも影響するため注意する。

### 🔑 Secrets（英語アプリ用に追加）
- `ENGLISH_AUDIO_BUCKET`: 音声保存用の Cloud Storage バケット名（非公開バケット。サービスアカウントに書き込み権限が必要）
- `gcp_service_account`, `GEMINI_API_KEY` は Body Make と同じ値

### 🗄️ Firestore / Cloud Storage データ構造
1. `english_study_logs` (勉強ログ)
   - **ドキュメントID**: 自動生成
   - **フィールド**:
     - `date` (str): YYYY-MM-DD
     - `minutes` (float): 勉強時間 (分)
     - `skill` (str): 技能（学習の目的で1つだけ選択）「リスニング」「スピーキング」「リーディング」「ライティング」「語彙」「文法」「発音」
       ※ 技能別の合計が総勉強時間と一致するよう、複数選択にはしない
     - `content` (str): 勉強内容（自由入力）
     - `created_at` (TIMESTAMP): SERVER_TIMESTAMP
2. `english_speeches` (1分スピーチ)
   - **ドキュメントID**: 自動生成
   - **フィールド**:
     - `date` (str): YYYY-MM-DD
     - `audio_path` (str): Cloud Storage 内のパス（`english_speeches/{date}_{8桁hex}.{拡張子}`）。音声はアップロードされた元ファイルのまま保存
     - `audio_content_type` (str): 音声の Content-Type（m4a は `audio/mp4`）
     - `original_filename` (str): アップロード時のファイル名
     - `transcript` (str): 文字起こし（言いよどみも残す）
     - `natural_version` (str): 自然な英語に直したスピーチ全文
     - `suggestions` (list): より自然な言い回し `{original, better, reason}` のリスト
     - `scores` (map): `total`（総合）, `grammar`（文法）, `vocabulary`（語彙）, `fluency`（流暢さ）, `content`（内容の伝わりやすさ）, `pronunciation`（発音）。各0〜100の整数
     - `overall_comment` (str): 総評・次回へのアドバイス
     - `growth_comment` (str): 過去と比べて特筆すべき変化があるときのみ。なければ空文字
     - `created_at` (TIMESTAMP): SERVER_TIMESTAMP
3. `english_read_texts` (読み上げ用の英文)
   - **ドキュメントID**: 自動生成
   - **フィールド**:
     - `title` (str): タイトル（任意。空文字可）
     - `text` (str): 英文
     - `created_at` (TIMESTAMP): SERVER_TIMESTAMP（一覧は新しい順）
     - `updated_at` (TIMESTAMP): SERVER_TIMESTAMP

### 🧠 スピーチ分析の仕様（`english_ai.analyze_speech`）
- アップロード音声（ボイスメモの m4a 等）を WAV 16kHz モノラルに変換して Gemini に渡す
- 点数は CEFR に対応づけた基準（`SCORING_RUBRIC`）で採点する（100点＝教養あるネイティブ相当/C2上位、70〜84点＝C1、55〜69点＝B2 など）
- 成長コメント用に、過去スピーチの文字起こしと点数（直近4回＋約90日前に最も近い1回）を渡す。過去の音声そのものは渡さない

### 🖥️ 画面構成（タブ）
- **📝 勉強ログ**: 記録対象日・勉強時間（分）・技能（横並びラジオで1つ選択。未選択では保存不可）・勉強内容を入力。保存成功で入力欄をクリア。その日の記録一覧（合計時間表示）と編集ポップオーバー・削除
- **🎤 1分スピーチ**: 今週（月〜日・日本時間）の録音有無を表示（未録音なら「今週はまだ録音していません」）。スピーチ日を選び、音声ファイルをアップロード→Gemini分析→音声を Cloud Storage、結果を Firestore に保存→結果表示
- **📈 積み上げ**: 累計・今月・今週の時間と連続記録日数、日別ヒートマップ（過去16週・月曜始まり）、累計時間の推移、週ごとの技能別時間（過去12週・積み上げ棒）、技能別の累計時間
  - 技能の配色は `SKILL_COLORS` で固定（並び順＝`SKILLS`）
- **🔊 読み上げ**: タイトル（任意）と英文を入力して読み上げ・保存（保存成功で入力欄をクリア）。保存した英文の一覧（新しい順。タイトルがなければ本文の先頭40文字を表示）ごとに読み上げ・編集ポップオーバー・削除
- **🎧 スピーチ履歴**: 点数の推移（表示項目を選択、初期は総合のみ）、過去スピーチごとに音声再生・ダウンロード（iPhoneの「ファイル」に保存可）・分析結果・削除（確認チェック付き。音声ファイルも削除）

### 🛠️ 実装上の注意
- Streamlit Community Cloud のサーバーは UTC のため、「今日」「今週」は `today_jst()`（日本時間）で判定する
- スピーチ分析（1分ほどかかる）はバックグラウンドスレッドで実行する（`start_speech_job`）。画面は `st.fragment(run_every=3)` で進み具合を確認し、完了したら画面全体を更新する。
  通常の処理で分析すると、スマホの画面スリープ・再接続などで再実行が割り込んだ際に、エラーも出ずに結果の保存・表示が失われるため。
  スレッド内で動く `process_speech` / `english_ai` / `edb.upload_audio` / `edb.save_speech` では `st.*` の表示関数を呼ばない（失敗時は例外を送出）。
- 1分スピーチタブの分析結果は、セッションの結果がなければ今週保存済みの最新スピーチを表示する
- Cloud Storage のバケット接続（`english_db.get_bucket`）は、成功時のみ保持し失敗は保持しない（`st.cache_resource` で失敗を保持すると Secrets 修正後もアプリ再起動まで復旧しないため）。接続できない場合は1分スピーチタブの先頭に原因を表示する
- Secrets の `ENGLISH_AUDIO_BUCKET` など単独のキーは `[gcp_service_account]` などの見出しより上に書く（見出しより下に書くとその見出しの項目として扱われる）
- 画面スタイル（タイトル縮小・見出し縮小・横並びラジオの間隔）は Body Make アプリと揃える
- 英文の読み上げは `tts_player(text)`（ブラウザ内蔵の Web Speech API を `components.html` で埋め込み）。米国英語（`en-US`、Samantha 等の en-US 音声を優先）。速さは 0.5〜2.0 倍のスライダーで、ブラウザの localStorage に記憶して全プレーヤー共通にする。再生・速さ変更はブラウザ内で完結し Streamlit の再実行は起きない。長文は途中で止まるブラウザがあるため文ごとに分けて読み上げる
- 読み上げは「🔊 読み上げ」タブの英文と、スピーチ分析の「自然な英語に直したスピーチ全文」に付ける（「より自然な言い回し」には付けない）

---

# 5. 開発時の行動指針・重要ルール

【最優先行動ルール: ヒアリング・リスク確認】
1. **要件の明確化**: 開発者からの変更要望に抽象的な部分や複数の解釈が成り立つ場合は、実装前にヒアリングを行い要件を明確化すること。
2. **デグレード防止**: Firestoreのコレクション名/フィールド変更、型変更、Streamlitフォームの構成変更など、既存データとの互換性や動作を損なうリスクがある場合は、必ず事前に指摘し確認を取ること。
3. **ファイル分離の保持**: どのファイル（`firestore_db.py`, `ai_services.py`, `app.py`）に対する変更かを明確にし、アーキテクチャの統一感を維持すること。

【変更報告】
- 変更後は、どこをどう変更したか・その理由を簡潔に説明すること（全コードの提示は不要。変更はブランチにコミット・プッシュする）。

---

機密情報について：FirestoreサービスアカウントやGemini APIキーなどの実際の値はこのリポジトリには含まれていません。ローカル実行では .streamlit/secrets.toml を使用しますが、実キーをコード内やコミットに含めないでください。
