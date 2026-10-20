# Calorie

Streamlit 製の2つのアプリと、それらを1つに統合する新しい Web アプリ（`web/`・Next.js 版「Growth Log」）を収録しています。Firestore / Gemini の設定は共通です。

> 新しい Web アプリは移行中です（英語アプリから移行。Body Make は Streamlit 版を引き続き利用）。設定手順は下の「Growth Log（web/）のセットアップ」を参照してください。

| アプリ | 起動ファイル | 内容 |
| --- | --- | --- |
| AI Body Make & Habit Tracker | `app.py` | 食事・運動・習慣・体組成・ジャーナリングを記録し、Gemini で解析・フィードバック |
| English Growth Log | `english_app.py` | 英語の勉強ログと積み上げの可視化、週1回の1分スピーチ音声を Gemini で分析（文字起こし・自然な言い回し・点数）、英文の読み上げ（米国英語・速さ調整） |

- データベース: Google Cloud Firestore
- AI: Gemini（`google-genai` SDK）
- 音声ファイルの保存先（English Growth Log）: Google Cloud Storage
- デプロイ先: Streamlit Community Cloud

仕様（Firestore のデータ構造・画面構成・開発ルール）は [CLAUDE.md](CLAUDE.md) を参照してください。

## ファイル構成

| ファイル | 役割 |
| --- | --- |
| `app.py` | Streamlit の画面構築・タブ構成・セッション状態管理（メイン） |
| `firestore_db.py` | Firestore の初期化とデータ操作（CRUD） |
| `ai_services.py` | Gemini による解析・フィードバック生成 |
| `english_app.py` | English Growth Log の画面 |
| `english_db.py` | English Growth Log 用の Firestore 操作と Cloud Storage（音声）操作 |
| `english_ai.py` | 音声の WAV 変換と Gemini による1分スピーチ分析 |
| `requirements.txt` | 依存パッケージ |

## ローカルでの実行手順

1. 依存パッケージをインストールします。

   ```bash
   pip install -r requirements.txt
   ```

2. `.streamlit/secrets.toml` を作成し、認証情報を設定します（下記「secrets.toml の書き方」参照）。

3. アプリを起動します。

   ```bash
   streamlit run app.py          # AI Body Make & Habit Tracker
   streamlit run english_app.py  # English Growth Log
   ```

   ブラウザで http://localhost:8501 が開きます。

## secrets.toml の書き方

`.streamlit/secrets.toml` は `.gitignore` で除外されており、**Git にはコミットされません**。実際のキーはこのファイル（または Streamlit Cloud の Secrets 設定）にのみ記載してください。

```toml
# Gemini API キー
GEMINI_API_KEY = "ここに Gemini API キー"

# 音声保存用の Cloud Storage バケット名（English Growth Log のみ使用）
ENGLISH_AUDIO_BUCKET = "ここにバケット名"

# Firestore サービスアカウント（GCP でダウンロードした JSON キーの内容）
[gcp_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "...@your-project-id.iam.gserviceaccount.com"
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
```

`GEMINI_API_KEY` や `ENGLISH_AUDIO_BUCKET` のような単独のキーは、必ず `[gcp_service_account]` の行より**上**に書いてください。見出しより下に書くと、その見出しの項目として扱われてアプリから読み込めません。

`gcp_service_account` は、上記のような TOML のテーブル形式のほか、JSON キーの中身をそのまま文字列として貼り付ける形式にも対応しています。

## Streamlit Community Cloud へのデプロイ

アプリごとに別々のアプリとしてデプロイします（Secrets もアプリごとに設定します）。

1. Streamlit Community Cloud でこのリポジトリを選び、メインファイルに `app.py`（または `english_app.py`）を指定します。
2. アプリの **Settings → Secrets** に、上記 `secrets.toml` と同じ内容を貼り付けます。

### English Growth Log の追加設定

1. GCP コンソールの Cloud Storage で、音声保存用のバケットを作成します（公開アクセスの防止は有効のまま）。
2. バケットの「権限」で、サービスアカウント（`gcp_service_account` の `client_email`）に「Storage オブジェクト ユーザー」ロールを付与します。
3. Secrets の先頭に `ENGLISH_AUDIO_BUCKET = "バケット名"` を追加します。

## Growth Log（web/）のセットアップ

Streamlit 版の起動待ちをなくすため、Vercel（無料プラン）で動く Next.js 製の Web アプリに作り直しています。iPhone ではホーム画面に追加してアプリのように使えます。

### 1. Google ログイン用の OAuth クライアントを作る（GCP コンソール）

1. 「API とサービス」→「OAuth 同意画面」で、ユーザーの種類「外部」を選んで作成します（アプリ名・メールアドレスを入力。公開ステータスは「テスト」のままで構いません）。
2. 「テストユーザー」に自分の Google アカウントを追加します。
3. 「認証情報」→「認証情報を作成」→「OAuth クライアント ID」→ 種類「ウェブ アプリケーション」で作成します。
4. 「承認済みのリダイレクト URI」に `https://<Vercel のドメイン>/api/auth/callback/google` を追加します（ドメインは手順2で決まります。ローカルで試す場合は `http://localhost:3000/api/auth/callback/google` も追加）。
5. 表示されたクライアント ID とクライアント シークレットを控えます。

### 2. Vercel にデプロイする

1. https://vercel.com に GitHub アカウントでサインアップします（Hobby プラン・無料）。
2. 「Add New… → Project」でこのリポジトリを選び、**Root Directory に `web`** を指定します。
3. 「Environment Variables」に `web/.env.example` の項目を設定します。
   - `GCP_PROJECT_ID` / `GCP_CLIENT_EMAIL` / `GCP_PRIVATE_KEY` は Streamlit の Secrets の `[gcp_service_account]` の `project_id` / `client_email` / `private_key` の値です。
   - `NEXTAUTH_SECRET` は任意のランダムな文字列（32文字以上）、`NEXTAUTH_URL` は `https://<Vercel のドメイン>` です。
   - `ALLOWED_EMAILS` にはログインを許可する自分の Google アカウントを書きます。
4. 「Deploy」を押します。表示されたドメインを手順1-4のリダイレクト URI に追加します。

### 3. iPhone のホーム画面に追加する

Safari でアプリを開き、共有ボタン →「ホーム画面に追加」を選びます。

### ローカルでの実行

```bash
cd web
npm install
cp .env.example .env.local   # 値を設定（MOCK_BACKEND=1 にするとダミーデータ・ログインなしで動く）
npm run dev                  # http://localhost:3000
```

