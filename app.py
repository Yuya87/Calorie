import streamlit as st
import pandas as pd
import plotly.express as px
from PIL import Image
import io
import json
from google.cloud import firestore
from google.oauth2 import service_account
from gemini_helper import analyze_meal_or_chat

st.set_page_config(page_title="AIボディメイク", layout="wide")
st.title("🏃 AIボディメイク")

# --- Firestore初期化 ---
@st.cache_resource
def get_db():
    sec = st.secrets["gcp_service_account"]
    key_dict = dict(sec)

    if "private_key" in key_dict:
        key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")

    creds = service_account.Credentials.from_service_account_info(key_dict)
    
    # 修正前: return firestore.Client(credentials=creds, project=key_dict["project_id"])
    # 修正後: database="calorie" を追加して指定のデータベースに接続する
    return firestore.Client(credentials=creds, project=key_dict["project_id"], database="calorie")
    
db = get_db()

def get_current_goals():
    docs = db.collection("user_goals").order_by("updated_at", direction=firestore.Query.DESCENDING).limit(1).get()
    if docs:
        return docs[0].to_dict()
    return {"target_cal": 2000, "target_p": 120, "target_f": 50, "target_c": 200}

def get_latest_bmr():
    docs = db.collection("body_composition").order_by("date", direction=firestore.Query.DESCENDING).limit(1).get()
    if docs:
        data = docs[0].to_dict()
        if data.get("bmr"):
            return float(data["bmr"])
        elif data.get("weight"):
            return round(float(data["weight"]) * 21.5, 0)
    return 1500.0

def update_goals(cal, p, f, c):
    db.collection("user_goals").add({
        "target_cal": cal, "target_p": p, "target_f": f, "target_c": c,
        "updated_at": firestore.SERVER_TIMESTAMP
    })

def get_recent_logs_for_context():
    """直近の食事・運動ログをドキュメントID付きで取得してGeminiへの文脈として提供"""
    meals_docs = db.collection("meals").order_by("created_at", direction=firestore.Query.DESCENDING).limit(15).get()
    ex_docs = db.collection("exercises").order_by("created_at", direction=firestore.Query.DESCENDING).limit(15).get()

    logs = []
    for d in meals_docs:
        data = d.to_dict()
        data["doc_id"] = d.id
        data["collection"] = "meals"
        logs.append(data)

    for d in ex_docs:
        data = d.to_dict()
        data["doc_id"] = d.id
        data["collection"] = "exercises"
        logs.append(data)

    return logs

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "こんにちは！AIボディメイクアシスタントです。食事や運動ログの登録、修正、削除など気軽にお申し付けください！"}
    ]

current_goals = get_current_goals()
latest_bmr = get_latest_bmr()

# サイドバー設定
st.sidebar.header("🎯 目標設定")
with st.sidebar.form("goal_form"):
    new_cal = st.number_input("目標摂取カロリー (kcal)", value=float(current_goals['target_cal']), step=50.0)
    new_p = st.number_input("目標 P (g)", value=float(current_goals['target_p']), step=5.0)
    new_f = st.number_input("目標 F (g)", value=float(current_goals['target_f']), step=5.0)
    new_c = st.number_input("目標 C (g)", value=float(current_goals['target_c']), step=5.0)
    if st.form_submit_button("目標を更新"):
        update_goals(new_cal, new_p, new_f, new_c)
        st.sidebar.success("目標を更新しました！")
        st.rerun()

st.sidebar.divider()
st.sidebar.metric("現在の適用基礎代謝 (BMR)", f"{latest_bmr:.0f} kcal", help="タニタの体組成データより自動適用中")

tab1, tab2, tab3, tab4 = st.tabs(["💬 AI対話・記録", "📊 栄養・アルコール管理", "🔥 カロリー収支 & 運動", "⚖️ 体組成 (タニタ)"])

# --- TAB 1: AI対話 ---
with tab1:
    st.header("AIアシスタントと会話して記録・修正")
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    uploaded_img = st.file_uploader("写真を送信", type=["jpg", "jpeg", "png"], key="meal_photo")
    image_obj = Image.open(uploaded_img) if uploaded_img else None

    user_input = st.chat_input("例: 昨日の夜にラーメンを食べた / さっきのハイボールの記録を削除して")

    if user_input or (uploaded_img and st.button("写真を送信")):
        input_text = user_input if user_input else "写真を送信しました。"
        st.session_state.messages.append({"role": "user", "content": input_text})
        with st.chat_message("user"):
            st.write(input_text)

        with st.chat_message("assistant"):
            with st.spinner("思考・解析中..."):
                recent_logs = get_recent_logs_for_context()
                res = analyze_meal_or_chat(
                    st.session_state.messages,
                    user_text=input_text,
                    image=image_obj,
                    existing_logs=recent_logs
                )

                response_text = res.get("assistant_response", "了解しました！")
                action_type = res.get("action_type", "GENERAL_CHAT")
                target_date = res.get("target_date") or pd.Timestamp.now().strftime('%Y-%m-%d')

                # 食事ログ追加
                if action_type == "MEAL_LOG" and res.get("meal_data"):
                    m = res["meal_data"]
                    db.collection("meals").add({
                        "date": target_date,
                        "food_name": m.get('food_name', '食事'),
                        "calories": float(m.get('calories', 0)),
                        "protein": float(m.get('protein', 0)),
                        "fat": float(m.get('fat', 0)),
                        "carbs": float(m.get('carbs', 0)),
                        "alcohol_g": float(m.get('alcohol_g', 0)),
                        "created_at": firestore.SERVER_TIMESTAMP
                    })
                    alc_info = f" (純アルコール: {m.get('alcohol_g', 0)}g)" if m.get('alcohol_g', 0) > 0 else ""
                    response_text += f"\n\n✅ **食事記録完了 [{target_date}]**: {m.get('food_name')} ({m.get('calories')}kcal / P:{m.get('protein')}g F:{m.get('fat')}g C:{m.get('carbs')}g){alc_info}"

                # 運動ログ追加
                elif action_type == "EXERCISE_LOG" and res.get("exercise_data"):
                    e = res["exercise_data"]
                    db.collection("exercises").add({
                        "date": target_date,
                        "exercise_name": e.get('exercise_name', '運動'),
                        "duration_min": float(e.get('duration_min', 0)),
                        "burned_calories": float(e.get('burned_calories', 0)),
                        "created_at": firestore.SERVER_TIMESTAMP
                    })
                    response_text += f"\n\n🏋️ **運動記録完了 [{target_date}]**: {e.get('exercise_name')} {e.get('duration_min')}分 ({e.get('burned_calories')}kcal消費)"

                # ログの更新 (パターンB)
                elif action_type == "UPDATE_LOG" and res.get("target_doc_id") and res.get("target_collection"):
                    coll = res["target_collection"]
                    doc_id = res["target_doc_id"]
                    doc_ref = db.collection(coll).document(doc_id)

                    update_fields = {}
                    if coll == "meals" and res.get("meal_data"):
                        m = res["meal_data"]
                        for k in ['food_name', 'calories', 'protein', 'fat', 'carbs', 'alcohol_g']:
                            if k in m: update_fields[k] = m[k]
                    elif coll == "exercises" and res.get("exercise_data"):
                        e = res["exercise_data"]
                        for k in ['exercise_name', 'duration_min', 'burned_calories']:
                            if k in e: update_fields[k] = e[k]

                    if update_fields:
                        doc_ref.update(update_fields)
                        response_text += f"\n\n✏️ **ログ修正完了** (ID: {doc_id})"

                # ログの削除 (パターンB)
                elif action_type == "DELETE_LOG" and res.get("target_doc_id") and res.get("target_collection"):
                    coll = res["target_collection"]
                    doc_id = res["target_doc_id"]
                    db.collection(coll).document(doc_id).delete()
                    response_text += f"\n\n🗑️ **ログ削除完了** (ID: {doc_id})"

                # 目標設定の更新
                elif action_type == "UPDATE_GOAL" and res.get("goal_data"):
                    g = res["goal_data"]
                    update_goals(g.get("target_cal", current_goals['target_cal']),
                                 g.get("target_p", current_goals['target_p']),
                                 g.get("target_f", current_goals['target_f']),
                                 g.get("target_c", current_goals['target_c']))
                    response_text += f"\n\n🎯 **目標設定更新完了**"
                    st.rerun()

                st.write(response_text)
                st.session_state.messages.append({"role": "assistant", "content": response_text})

# --- TAB 2: 栄養＆アルコール管理 ---
with tab2:
    st.header("日別PFC ＆ アルコール摂取推移")
    docs = db.collection("meals").get()
    meal_list = [d.to_dict() for d in docs]

    if meal_list:
        df_m = pd.DataFrame(meal_list)

        for col in ['calories', 'protein', 'fat', 'carbs', 'alcohol_g']:
            if col in df_m.columns:
                df_m[col] = pd.to_numeric(df_m[col], errors='coerce').fillna(0)

        df_meals = df_m.groupby('date').agg({
            'calories': 'sum', 'protein': 'sum', 'fat': 'sum', 'carbs': 'sum', 'alcohol_g': 'sum'
        }).reset_index().sort_values('date')

        latest = df_meals.iloc[-1]
        st.subheader(f"📊 最新日 ({latest['date']}) の達成状況")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("摂取カロリー", f"{latest['calories']:.0f} kcal", f"{latest['calories'] - current_goals['target_cal']:.0f} kcal")
        c2.metric("Protein (P)", f"{latest['protein']:.1f} g", f"{latest['protein'] - current_goals['target_p']:.1f} g")
        c3.metric("Fat (F)", f"{latest['fat']:.1f} g", f"{latest['fat'] - current_goals['target_f']:.1f} g")
        c4.metric("Carbs (C)", f"{latest['carbs']:.1f} g", f"{latest['carbs'] - current_goals['target_c']:.1f} g")
        c5.metric("純アルコール", f"{latest['alcohol_g']:.1f} g")

        st.plotly_chart(px.bar(df_meals, x='date', y=['protein', 'fat', 'carbs'], title="日別 PFC摂取量 (g)"), use_container_width=True)
        st.plotly_chart(px.bar(df_meals, x='date', y='alcohol_g', title="アルコール摂取量 (g)", color_discrete_sequence=['#FFA500']), use_container_width=True)
    else:
        st.info("データがまだありません。")

# --- TAB 3: カロリー収支＆運動 ---
with tab3:
    st.header("🔥 カロリー収支")
    m_docs = [d.to_dict() for d in db.collection("meals").get()]
    e_docs = [d.to_dict() for d in db.collection("exercises").get()]
    b_docs = [d.to_dict() for d in db.collection("body_composition").get()]

    df_in = pd.DataFrame(m_docs).groupby('date')['calories'].sum().reset_index() if m_docs else pd.DataFrame(columns=['date', 'calories'])
    df_ex = pd.DataFrame(e_docs).groupby('date')['burned_calories'].sum().reset_index() if e_docs else pd.DataFrame(columns=['date', 'burned_calories'])
    df_bmr = pd.DataFrame(b_docs)[['date', 'bmr']] if b_docs and 'bmr' in pd.DataFrame(b_docs).columns else pd.DataFrame(columns=['date', 'bmr'])

    if not df_in.empty or not df_ex.empty:
        df_bal = pd.merge(df_in, df_ex, on='date', how='outer').fillna(0)
        df_bal = pd.merge(df_bal, df_bmr, on='date', how='left') if not df_bmr.empty else df_bal
        df_bal['bmr'] = df_bal['bmr'].fillna(latest_bmr) if 'bmr' in df_bal.columns else latest_bmr

        for col in ['calories', 'burned_calories', 'bmr']:
            if col in df_bal.columns:
                df_bal[col] = pd.to_numeric(df_bal[col], errors='coerce').fillna(0)

        df_bal['total_burn'] = df_bal['bmr'] + df_bal['burned_calories']
        df_bal['net'] = df_bal['calories'] - df_bal['total_burn']
        df_bal = df_bal.sort_values('date')

        latest_b = df_bal.iloc[-1]
        b1, b2, b3, b4 = st.columns(4)
        b1.metric("摂取カロリー", f"{latest_b['calories']:.0f} kcal")
        b2.metric("基礎代謝", f"{latest_b['bmr']:.0f} kcal")
        b3.metric("運動消費", f"{latest_b['burned_calories']:.0f} kcal")
        b4.metric("収支 (摂取 - 総消費)", f"{latest_b['net']:.0f} kcal", delta=f"{latest_b['net']:.0f} kcal", delta_color="inverse")

        st.plotly_chart(px.bar(df_bal, x='date', y=['calories', 'total_burn'], barmode='group', title="日別 カロリー比較 (kcal)"), use_container_width=True)
    else:
        st.info("データがまだありません。")

# --- TAB 4: 体組成データ ---
with tab4:
    st.header("⚖️ タニタ体組成計 CSVアップロード")
    tanita_file = st.file_uploader("タニタのCSVファイルをアップロード", type=["csv"])

    if tanita_file:
        try:
            content = tanita_file.read()
            try:
                df_raw = pd.read_csv(io.BytesIO(content), encoding="shift_jis")
            except Exception:
                df_raw = pd.read_csv(io.BytesIO(content), encoding="utf-8")

            col_map = {}
            for c in df_raw.columns:
                c_str = str(c).lower()
                if "日付" in c_str or "date" in c_str or "測定日時" in c_str: col_map["date"] = c
                elif "体重" in c_str or "weight" in c_str: col_map["weight"] = c
                elif "体脂肪" in c_str or "fat" in c_str: col_map["body_fat"] = c
                elif "筋肉" in c_str or "muscle" in c_str: col_map["muscle_mass"] = c
                elif "基礎代謝" in c_str or "bmr" in c_str: col_map["bmr"] = c

            if "date" in col_map and "weight" in col_map:
                for _, row in df_raw.iterrows():
                    d_val = str(row[col_map["date"]]).split(" ")[0]
                    if d_val and pd.notnull(row[col_map["weight"]]):
                        doc_ref = db.collection("body_composition").document(d_val)
                        doc_ref.set({
                            "date": d_val,
                            "weight": float(row[col_map["weight"]]),
                            "body_fat": float(row[col_map["body_fat"]]) if "body_fat" in col_map and pd.notnull(row[col_map["body_fat"]]) else None,
                            "muscle_mass": float(row[col_map["muscle_mass"]]) if "muscle_mass" in col_map and pd.notnull(row[col_map["muscle_mass"]]) else None,
                            "bmr": float(row[col_map["bmr"]]) if "bmr" in col_map and pd.notnull(row[col_map["bmr"]]) else None,
                        }, merge=True)
                st.success("🎉 Firestoreに体組成データを保存しました！")
                st.rerun()
        except Exception as e:
            st.error(f"エラー: {e}")

    b_docs = [d.to_dict() for d in db.collection("body_composition").get()]
    if b_docs:
        df_body = pd.DataFrame(b_docs).sort_values('date')
        for col in ['weight', 'muscle_mass']:
            if col in df_body.columns:
                df_body[col] = pd.to_numeric(df_body[col], errors='coerce')
        st.plotly_chart(px.line(df_body, x='date', y=['weight', 'muscle_mass'], title="体重・筋肉量の推移 (kg)", markers=True), use_container_width=True)
