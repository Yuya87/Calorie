import json
import uuid
import streamlit as st
from google.cloud import firestore, storage
from google.oauth2 import service_account

# Firestore クライアントは Body Make アプリと共通の初期化処理を流用する
from firestore_db import db

# ---------------------------------------------------------
# Cloud Storage 初期化（音声ファイルの保存先）
# ---------------------------------------------------------
@st.cache_resource
def init_storage_bucket():
    """GCS バケットの初期化。バケット名は st.secrets["ENGLISH_AUDIO_BUCKET"] で指定"""
    try:
        bucket_name = st.secrets.get("ENGLISH_AUDIO_BUCKET", None)
        if not bucket_name:
            st.error("⚠️ Secrets に ENGLISH_AUDIO_BUCKET（音声保存用バケット名）を設定してください。")
            return None
        if "gcp_service_account" in st.secrets:
            secret_val = st.secrets["gcp_service_account"]
            key_dict = json.loads(secret_val) if isinstance(secret_val, str) else dict(secret_val)
            if "private_key" in key_dict and isinstance(key_dict["private_key"], str):
                key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
            creds = service_account.Credentials.from_service_account_info(key_dict)
            client = storage.Client(credentials=creds, project=key_dict.get("project_id"))
        else:
            client = storage.Client()
        return client.bucket(bucket_name)
    except Exception as e:
        st.error(f"⚠️ Cloud Storage初期化エラー: {e}")
        return None

bucket = init_storage_bucket()

def upload_audio(date_str, audio_bytes, ext, content_type):
    """音声をアップロードし、バケット内のパスを返す。失敗時は RuntimeError
    （スピーチ保存処理の途中で呼ばれるため st.* は呼ばない）"""
    if not bucket:
        raise RuntimeError("音声の保存先（Cloud Storage）が利用できません。ENGLISH_AUDIO_BUCKET を確認してください。")
    try:
        path = f"english_speeches/{date_str}_{uuid.uuid4().hex[:8]}.{ext}"
        bucket.blob(path).upload_from_string(audio_bytes, content_type=content_type)
        return path
    except Exception as e:
        raise RuntimeError(f"音声のアップロードに失敗しました: {e}") from e

@st.cache_data(show_spinner=False, max_entries=20)
def download_audio(path):
    """音声を取得（再生・ダウンロード用）。失敗時は None"""
    if not bucket or not path:
        return None
    try:
        return bucket.blob(path).download_as_bytes()
    except Exception as e:
        st.error(f"音声の取得に失敗しました: {e}")
        return None

def delete_audio(path):
    if bucket and path:
        try:
            bucket.blob(path).delete()
        except Exception as e:
            st.warning(f"音声ファイルの削除に失敗しました: {e}")

# ---------------------------------------------------------
# 勉強ログ (english_study_logs)
# ---------------------------------------------------------
def _with_id(docs):
    items = []
    for d in docs:
        item = d.to_dict()
        item["doc_id"] = d.id
        items.append(item)
    return items

def fetch_study_logs(date_str):
    if not db:
        return []
    try:
        return _with_id(db.collection("english_study_logs").where("date", "==", date_str).get())
    except Exception as e:
        st.error(f"勉強ログの取得エラー: {e}")
        return []

def fetch_all_study_logs():
    if not db:
        return []
    try:
        return _with_id(db.collection("english_study_logs").get())
    except Exception as e:
        st.error(f"勉強ログの取得エラー: {e}")
        return []

def save_study_log(log_data):
    if db:
        log_data["created_at"] = firestore.SERVER_TIMESTAMP
        db.collection("english_study_logs").add(log_data)

def update_study_log(doc_id, log_data):
    if db and doc_id:
        try:
            db.collection("english_study_logs").document(doc_id).update(log_data)
            return True
        except Exception as e:
            st.error(f"勉強ログの更新に失敗しました: {e}")
    return False

def delete_study_log(doc_id):
    if db and doc_id:
        try:
            db.collection("english_study_logs").document(doc_id).delete()
            return True
        except Exception as e:
            st.error(f"勉強ログの削除に失敗しました: {e}")
    return False

# ---------------------------------------------------------
# 1分スピーチ (english_speeches)
# ---------------------------------------------------------
def fetch_all_speeches():
    """全スピーチを日付昇順で返す"""
    if not db:
        return []
    try:
        items = _with_id(db.collection("english_speeches").get())
        return sorted(items, key=lambda s: s.get("date", ""))
    except Exception as e:
        st.error(f"スピーチデータの取得エラー: {e}")
        return []

def save_speech(speech_data):
    """スピーチを保存。失敗時は RuntimeError（保存処理の途中で呼ばれるため st.* は呼ばない）"""
    if not db:
        raise RuntimeError("Firestore が利用できません。")
    try:
        db.collection("english_speeches").add(dict(speech_data, created_at=firestore.SERVER_TIMESTAMP))
    except Exception as e:
        raise RuntimeError(f"スピーチの保存に失敗しました: {e}") from e

def delete_speech(doc_id, audio_path):
    """スピーチの記録と音声ファイルを削除"""
    if db and doc_id:
        try:
            db.collection("english_speeches").document(doc_id).delete()
            delete_audio(audio_path)
            return True
        except Exception as e:
            st.error(f"スピーチの削除に失敗しました: {e}")
    return False
