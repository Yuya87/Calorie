import json
import streamlit as st
from google.cloud import firestore
from google.oauth2 import service_account

# ---------------------------------------------------------
# Firestore 初期化
# ---------------------------------------------------------
@st.cache_resource
def init_firestore():
    """GCP Firestore クライアントの初期化"""
    try:
        if "gcp_service_account" in st.secrets:
            secret_val = st.secrets["gcp_service_account"]
            if isinstance(secret_val, str):
                key_dict = json.loads(secret_val)
            else:
                key_dict = dict(secret_val)
            
            if "private_key" in key_dict and isinstance(key_dict["private_key"], str):
                pk = key_dict["private_key"]
                if "\\n" in pk:
                    key_dict["private_key"] = pk.replace("\\n", "\n")
                
            creds = service_account.Credentials.from_service_account_info(key_dict)
            return firestore.Client(credentials=creds, project=key_dict.get("project_id"))
        else:
            return firestore.Client()
    except Exception as e:
        st.error(f"⚠️ Firestore初期化エラー: Secretsの設定またはPrivateKeyを確認してください。({e})")
        return None

db = init_firestore()

# ---------------------------------------------------------
# 目標設定 (user_goals)
# ---------------------------------------------------------
def fetch_user_goals():
    if not db:
        return {"target_cal": 2200, "target_p": 160, "target_f": 50, "target_c": 250}
    try:
        docs = db.collection("user_goals").order_by("updated_at", direction=firestore.Query.DESCENDING).limit(1).get()
        for doc in docs:
            return doc.to_dict()
    except Exception as e:
        st.warning(f"目標設定の取得に失敗しました: {e}")
    return {"target_cal": 2200, "target_p": 160, "target_f": 50, "target_c": 250}

def save_user_goals(cal, p, f, c):
    if db:
        db.collection("user_goals").add({
            "target_cal": float(cal),
            "target_p": float(p),
            "target_f": float(f),
            "target_c": float(c),
            "updated_at": firestore.SERVER_TIMESTAMP
        })

# ---------------------------------------------------------
# 単語辞書・ルール (user_rules)
# ---------------------------------------------------------
def fetch_user_rules():
    if not db:
        return []
    try:
        docs = db.collection("user_rules").get()
        rules = []
        for d in docs:
            r = d.to_dict()
            r["doc_id"] = d.id
            rules.append(r)
        return rules
    except Exception as e:
        return []

def save_user_rule(title, detail):
    if db and title and detail:
        db.collection("user_rules").add({
            "title": title,
            "detail": detail,
            "created_at": firestore.SERVER_TIMESTAMP
        })

def delete_user_rule(doc_id):
    if db and doc_id:
        db.collection("user_rules").document(doc_id).delete()

# ---------------------------------------------------------
# 食事ログ (meals)
# ---------------------------------------------------------
def fetch_daily_meals(selected_date_str):
    if not db:
        return []
    try:
        docs = db.collection("meals").where("date", "==", selected_date_str).get()
        meals = []
        for d in docs:
            m = d.to_dict()
            m["doc_id"] = d.id
            meals.append(m)
        return meals
    except Exception as e:
        st.error(f"食事データの取得エラー: {e}")
        return []

def fetch_meals_range(start_date_str, end_date_str):
    if not db:
        return []
    try:
        docs = db.collection("meals")\
            .where("date", ">=", start_date_str)\
            .where("date", "<=", end_date_str).get()
        return [d.to_dict() for d in docs]
    except Exception as e:
        st.error(f"期間食事データの取得エラー: {e}")
        return []

def save_meal_record(meal_data):
    if db:
        meal_data["created_at"] = firestore.SERVER_TIMESTAMP
        db.collection("meals").add(meal_data)

def update_meal(doc_id, meal_data):
    if db and doc_id:
        try:
            db.collection("meals").document(doc_id).update(meal_data)
            return True
        except Exception as e:
            st.error(f"食事データの更新に失敗しました: {e}")
    return False

def delete_meal(doc_id):
    if db and doc_id:
        try:
            db.collection("meals").document(doc_id).delete()
            return True
        except Exception as e:
            st.error(f"食事データの削除に失敗しました: {e}")
    return False

# ---------------------------------------------------------
# 運動ログ (exercises)
# ---------------------------------------------------------
def fetch_daily_exercises(selected_date_str):
    if not db:
        return []
    try:
        docs = db.collection("exercises").where("date", "==", selected_date_str).get()
        return [d.to_dict() for d in docs]
    except Exception as e:
        st.error(f"運動データの取得エラー: {e}")
        return []

def save_exercise_record(exercise_data):
    if db:
        exercise_data["created_at"] = firestore.SERVER_TIMESTAMP
        db.collection("exercises").add(exercise_data)

# ---------------------------------------------------------
# 体組成データ (body_composition)
# ---------------------------------------------------------
def fetch_body_comp(selected_date_str):
    if not db:
        return None
    try:
        doc = db.collection("body_composition").document(selected_date_str).get()
        return doc.to_dict() if doc.exists else None
    except Exception as e:
        return None

def fetch_all_body_comp():
    if not db:
        return []
    try:
        docs = db.collection("body_composition").get()
        return [d.to_dict() for d in docs]
    except Exception as e:
        return []

def save_batch_body_comp(df_daily, weight_col, fat_col, muscle_col, bmr_col):
    if not db:
        return 0
    batch = db.batch()
    count = 0
    for _, row in df_daily.iterrows():
        doc_ref = db.collection("body_composition").document(row['date_str'])
        batch.set(doc_ref, {
            "date": row['date_str'],
            "weight": float(row[weight_col]),
            "body_fat": float(row[fat_col]) if fat_col and pd.notnull(row[fat_col]) else 0.0,
            "muscle_mass": float(row[muscle_col]) if muscle_col and pd.notnull(row[muscle_col]) else 0.0,
            "bmr": float(row[bmr_col]) if bmr_col and pd.notnull(row[bmr_col]) else 0.0,
            "updated_at": firestore.SERVER_TIMESTAMP
        }, merge=True)
        count += 1
    batch.commit()
    return count

# ---------------------------------------------------------
# ジャーナル (journals)
# ---------------------------------------------------------
def fetch_journal(selected_date_str):
    if not db:
        return None
    try:
        doc = db.collection("journals").document(selected_date_str).get()
        return doc.to_dict() if doc.exists else None
    except Exception as e:
        return None

def save_journal(selected_date_str, note, ai_feedback=""):
    if db:
        db.collection("journals").document(selected_date_str).set({
            "date": selected_date_str,
            "note": note,
            "ai_feedback": ai_feedback,
            "updated_at": firestore.SERVER_TIMESTAMP
        }, merge=True)

# ---------------------------------------------------------
# 習慣化チェックイン (daily_habits)
# ---------------------------------------------------------
def fetch_daily_habit(selected_date_str):
    if not db:
        return {"gym": "未記録", "english": "未記録", "rest_day": "未記録", "memo": ""}
    try:
        doc = db.collection("daily_habits").document(selected_date_str).get()
        if doc.exists:
            return doc.to_dict()
    except Exception as e:
        pass
    return {"gym": "未記録", "english": "未記録", "rest_day": "未記録", "memo": ""}

def save_daily_habit(selected_date_str, gym_status, english_status, rest_status, memo=""):
    if db:
        db.collection("daily_habits").document(selected_date_str).set({
            "date": selected_date_str,
            "gym": gym_status,
            "english": english_status,
            "rest_day": rest_status,
            "memo": memo,
            "updated_at": firestore.SERVER_TIMESTAMP
        }, merge=True)

def fetch_habits_range(start_date_str, end_date_str):
    if not db:
        return []
    try:
        docs = db.collection("daily_habits")\
            .where("date", ">=", start_date_str)\
            .where("date", "<=", end_date_str).get()
        return [d.to_dict() for d in docs]
    except Exception as e:
        return []