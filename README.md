# Calorie

食事・運動・習慣・体組成・ジャーナリングを記録し、Gemini で解析・フィードバックする Streamlit 製のカロリー管理アプリです。

- データベース: Google Cloud Firestore
- AI: Gemini（`google-genai` SDK）
- デプロイ先: Streamlit Community Cloud

仕様（Firestore のデータ構造・画面構成・開発ルール）は [CLAUDE.md](CLAUDE.md) を参照してください。

## ファイル構成

| ファイル | 役割 |
| --- | --- |
| `app.py` | Streamlit の画面構築・タブ構成・セッション状態管理（メイン） |
| `firestore_db.py` | Firestore の初期化とデータ操作（CRUD） |
| `ai_services.py` | Gemini による解析・フィードバック生成 |
| `requirements.txt` | 依存パッケージ |

## ローカルでの実行手順

1. 依存パッケージをインストールします。

   ```bash
   pip install -r requirements.txt
   ```

2. `.streamlit/secrets.toml` を作成し、認証情報を設定します（下記「secrets.toml の書き方」参照）。

3. アプリを起動します。

   ```bash
   streamlit run app.py
   ```

   ブラウザで http://localhost:8501 が開きます。

## secrets.toml の書き方

`.streamlit/secrets.toml` は `.gitignore` で除外されており、**Git にはコミットされません**。実際のキーはこのファイル（または Streamlit Cloud の Secrets 設定）にのみ記載してください。

```toml
# Gemini API キー
GEMINI_API_KEY = "ここに Gemini API キー"

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

`gcp_service_account` は、上記のような TOML のテーブル形式のほか、JSON キーの中身をそのまま文字列として貼り付ける形式にも対応しています。

## Streamlit Community Cloud へのデプロイ

1. Streamlit Community Cloud でこのリポジトリを選び、メインファイルに `app.py` を指定します。
2. アプリの **Settings → Secrets** に、上記 `secrets.toml` と同じ内容を貼り付けます。
