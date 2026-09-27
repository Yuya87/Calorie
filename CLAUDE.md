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
- 登録成功後の入力欄クリアは、保存時にフラグ（例: `clear_meal_inputs`）を立てて `st.rerun()` し、次回描画でウィジェット生成前に該当keyを `session_state` から削除する（生成後のkeyへの代入はエラーになる）。
- スマホ表示を考慮し、ラジオボタンは `horizontal=True` で横並びにする。タイトルは `st.title` ではなくCSSで縮小した見出しを使い、上部余白も詰めている。

---

# 4. 開発時の行動指針・重要ルール

【最優先行動ルール: ヒアリング・リスク確認】
1. **要件の明確化**: 開発者からの変更要望に抽象的な部分や複数の解釈が成り立つ場合は、実装前にヒアリングを行い要件を明確化すること。
2. **デグレード防止**: Firestoreのコレクション名/フィールド変更、型変更、Streamlitフォームの構成変更など、既存データとの互換性や動作を損なうリスクがある場合は、必ず事前に指摘し確認を取ること。
3. **ファイル分離の保持**: どのファイル（`firestore_db.py`, `ai_services.py`, `app.py`）に対する変更かを明確にし、アーキテクチャの統一感を維持すること。

【変更報告】
- 変更後は、どこをどう変更したか・その理由を簡潔に説明すること（全コードの提示は不要。変更はブランチにコミット・プッシュする）。

---

機密情報について：FirestoreサービスアカウントやGemini APIキーなどの実際の値はこのリポジトリには含まれていません。ローカル実行では .streamlit/secrets.toml を使用しますが、実キーをコード内やコミットに含めないでください。
