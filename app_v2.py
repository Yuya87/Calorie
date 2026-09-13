import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date, timedelta
from google.cloud import firestore
from google.oauth2 import service_account
from google import genai
from google.genai import types

# ---------------------------------------------------------
# 1. ページ基本設定 & セッション状態初期化
# ---------------------------------------------------------
st.set_page_config(
    page_title="AI Body Make & Habit Tracker",
    page_icon="💪",
    layout="wide"
)

# ---------------------------------------------------------
# 2. クラウドサービス接続・クライアント初期化
# ---------------------------------------------------------
@st.cache_resource
def init_firestore():
    key_dict = dict(st.secrets["gcp_service_account"])
    # Secrets読み込み時の改行コードエスケープを補正
    if "private_key" in key_dict:
        key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
    credentials = service_account.Credentials.from_service_account_info(key_dict)
    return firestore.Client(credentials=credentials, project=key_dict["project_id"])

db = init_firestore()

@st.cache_resource
def init_genai():
    api_key = st.secrets["GEMINI_API_KEY"]
    return genai.Client(api_key=api_key)

ai_client = init_genai()

# ---------------------------------------------------------
# 3. Firestore ヘルパー関数
# ---------------------------------------------------------
def get_latest_user_goals():
    docs = db.collection("user_goals").order_by("updated_at", direction=firestore.Query.DESCENDING).limit(1).get()
    if docs:
        return docs[0].to_dict()
    return {"target_cal": 2000.0, "target_p": 120.0, "target_f": 55.0, "target_c": 250.0}

def save_user_goals(cal, p, f, c):
    db.collection("user_goals").add({
        "target_cal": float(cal),
        "target_p": float(p),
        "target_f": float(f),
        "target_c": float(c),
        "updated_at": firestore.SERVER_TIMESTAMP
    })

def get_daily_habits(target_date_str):
    doc = db.collection("daily_habits").document(target_date_str).get()
    if doc.exists:
        return doc.to_dict()
    return {"gym": "未記録", "english": "未記録", "rest_day": "未記録", "memo": ""}

def save_daily_habits(target_date_str, gym, english, rest_day, memo):
    db.collection("daily_habits").document(target_date_str).set({
        "date": target_date_str,
        "gym": gym,
        "english": english,
        "rest_day": rest_day,
        "memo": memo,
        "updated_at": firestore.SERVER_TIMESTAMP
    }, merge=True)

def get_meals_by_date(target_date_str):
    docs = db.collection("meals").where("date", "==", target_date_str).get()
    return [{"id": d.id, **d.to_dict()} for d in docs]

def save_meal_item(meal_data):
    db.collection("meals").add({
        **meal_data,
        "created_at": firestore.SERVER_TIMESTAMP
    })

def delete_meal_item(doc_id):
    db.collection("meals").document(doc_id).delete()

def get_exercises_by_date(target_date_str):
    docs = db.collection("exercises").where("date", "==", target_date_str).get()
    return [{"id": d.id, **d.to_dict()} for d in docs]

def save_exercise_item(exercise_data):
    db.collection("exercises").add({
        **exercise_data,
        "created_at": firestore.SERVER_TIMESTAMP
    })

def delete_exercise_item(doc_id):
    db.collection("exercises").document(doc_id).delete()

def get_journal(target_date_str):
    doc = db.collection("journals").document(target_date_str).get()
    if doc.exists:
        return doc.to_dict()
    return {"note": "", "ai_feedback": ""}

def save_journal(target_date_str, note, ai_feedback=""):
    db.collection("journals").document(target_date_str).set({
        "date": target_date_str,
        "note": note,
        "ai_feedback": ai_feedback,
        "updated_at": firestore.SERVER_TIMESTAMP
    }, merge=True)

def save_body_composition_batch(df):
    batch = db.batch()
    for _, row in df.iterrows():
        d_str = str(row["date"])
        doc_ref = db.collection("body_composition").document(d_str)
        data = {
            "date": d_str,
            "weight": float(row["weight"]) if pd.notnull(row.get("weight")) else None,
            "body_fat": float(row["body_fat"]) if pd.notnull(row.get("body_fat")) else None,
            "muscle_mass": float(row["muscle_mass"]) if pd.notnull(row.get("muscle_mass")) else None,
            "bmr": float(row["bmr"]) if pd.notnull(row.get("bmr")) else None,
            "updated_at": firestore.SERVER_TIMESTAMP
        }
        batch.set(doc_ref, data, merge=True)
    batch.commit()

# ---------------------------------------------------------
# 4. AI (Gemini 3.6 Flash) 解析関数
# ---------------------------------------------------------
def parse_meal_text_with_ai(text):
    prompt = f"""
    以下の食事記録テキストを解析し、JSONフォーマットのみを出力してください。
    テキスト: "{text}"

    出力フォーマット例:
    {{
        "meal_type": "昼食",
        "food_name": "蒸し鶏とブロッコリーのサラダ",
        "calories": 350.0,
        "protein": 40.0,
        "fat": 8.0,
        "carbs": 12.0,
        "alcohol_g": 0.0
    }}
    """
    response = ai_client.models.generate_content(
        model='gemini-3.6-flash',
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    import json
    return json.loads(response.text)

def parse_exercise_text_with_ai(text):
    prompt = f"""
    以下の運動記録テキストを解析し、JSONフォーマットのみを出力してください。
    テキスト: "{text}"

    出力フォーマット例:
    {{
        "exercise_name": "傾斜ウォーキング",
        "duration_min": 45.0,
        "burned_calories": 300.0
    }}
    """
    response = ai_client.models.generate_content(
        model='gemini-3.6-flash',
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    import json
    return json.loads(response.text)

def generate_journal_feedback(note, meals, exercises, habits):
    prompt = f"""
    あなたは親切でプロフェッショナルなAIボディメイクコーチです。
    ユーザーの本日の振り返りと記録データに基づいて、短く前向きで実用的なアドバイスを行ってください。

    【本日のデータ】
    - 振り返りメモ: {note}
    - 習慣ステータス: 運動={habits.get('gym')}, 英語学習={habits.get('english')}, 休肝日={habits.get('rest_day')}
    - 食事件数: {len(meals)}件
    - 運動件数: {len(exercises)}件

    トーン: ポジティブ、具体的、アドバイスは200文字程度。
    """
    response = ai_client.models.generate_content(
        model='gemini-3.6-flash',
        contents=prompt
    )
    return response.text

# ---------------------------------------------------------
# 5. サイドバー (目標設定)
# ---------------------------------------------------------
current_goals = get_latest_user_goals()

st.sidebar.header("🎯 目標マクロ設定")
with st.sidebar.form("goals_form"):
    target_cal = st.number_input("目標カロリー (kcal)", value=float(current_goals.get("target_cal", 2000.0)), step=50.0)
    target_p = st.number_input("目標タンパク質 P (g)", value=float(current_goals.get("target_p", 120.0)), step=5.0)
    target_f = st.number_input("目標脂質 F (g)", value=float(current_goals.get("target_f", 55.0)), step=5.0)
    target_c = st.number_input("目標炭水化物 C (g)", value=float(current_goals.get("target_c", 250.0)), step=5.0)
    submit_goals = st.form_submit_button("目標を更新")

if submit_goals:
    save_user_goals(target_cal, target_p, target_f, target_c)
    st.sidebar.success("目標マクロを更新しました！")
    st.rerun()

# ---------------------------------------------------------
# 6. メインUI (タブ構成)
# ---------------------------------------------------------
st.title("💪 AI Body Make & Habit Tracker")

tab1, tab2, tab3, tab4 = st.tabs([
    "📝 本日のデータ入力", 
    "📊 日次サマリー＆KPI", 
    "📈 習慣＆体組成の分析", 
    "⚙️ 設定"
])

# =========================================================
# TAB 1: 📝 本日のデータ入力
# =========================================================
with tab1:
    selected_date = st.date_input("記録対象日", date.today())
    target_date_str = selected_date.strftime("%Y-%m-%d")

    st.subheader("🏋️ 1. 習慣化チェックイン")
    current_habits = get_daily_habits(target_date_str)
    
    habit_options = ["未記録", "目標達成", "一応やった", "未実施"]
    
    col_h1, col_h2, col_h3 = st.columns(3)
    with col_h1:
        gym_val = st.selectbox("🏋️ 筋トレ・運動", habit_options, index=habit_options.index(current_habits.get("gym", "未記録")))
    with col_h2:
        eng_val = st.selectbox("🔤 英語学習", habit_options, index=habit_options.index(current_habits.get("english", "未記録")))
    with col_h3:
        rest_val = st.selectbox("🍺 休肝日", habit_options, index=habit_options.index(current_habits.get("rest_day", "未記録")))
    
    memo_val = st.text_input("📝 習慣メモ", value=current_habits.get("memo", ""))
    
    if st.button("習慣化ステータスを保存"):
        save_daily_habits(target_date_str, gym_val, eng_val, rest_val, memo_val)
        st.success("習慣ステータスを更新しました！")

    st.divider()

    st.subheader("🥗 2. 食事ログの入力")
    registered_meals = get_meals_by_date(target_date_str)
    if registered_meals:
        st.markdown("**登録済みの食事:**")
        for m in registered_meals:
            col_m1, col_m2 = st.columns([4, 1])
            with col_m1:
                st.caption(f"・[{m.get('meal_type', '不明')}] {m.get('food_name')} | {m.get('calories',0)} kcal (P:{m.get('protein',0)}g F:{m.get('fat',0)}g C:{m.get('carbs',0)}g)")
            with col_m2:
                if st.button("削除", key=f"del_meal_{m['id']}"):
                    delete_meal_item(m['id'])
                    st.rerun()

    st.markdown("##### 🤖 AI自然言語入力")
    meal_text_input = st.text_input("例: 昼食に胸肉200gとブロッコリー、白米150gを食べた", key="meal_text_input")
    if st.button("AI解析して食事登録"):
        if meal_text_input:
            with st.spinner("AI解析中..."):
                parsed = parse_meal_text_with_ai(meal_text_input)
                parsed["date"] = target_date_str
                parsed["is_eating_out"] = False
                parsed["restaurant_name"] = ""
                parsed["dining_partners"] = ""
                parsed["eating_out_comment"] = ""
                save_meal_item(parsed)
                st.success(f"追加しました: {parsed.get('food_name')}")
                st.rerun()

    with st.expander("➕ 手動・外食詳細入力"):
        with st.form("manual_meal_form"):
            m_type = st.selectbox("区分", ["朝食", "昼食", "夕食", "間食"])
            f_name = st.text_input("品目名")
            c_cal = st.number_input("カロリー (kcal)", min_value=0.0, step=10.0)
            c_p = st.number_input("タンパク質 (g)", min_value=0.0, step=1.0)
            c_f = st.number_input("脂質 (g)", min_value=0.0, step=1.0)
            c_c = st.number_input("炭水化物 (g)", min_value=0.0, step=1.0)
            c_alc = st.number_input("アルコール量 (g)", min_value=0.0, step=1.0)
            is_out = st.checkbox("外食フラグ")
            r_name = st.text_input("店名・場所")
            d_partners = st.text_input("同行者")
            e_comment = st.text_area("外食メモ・評価")
            
            submit_meal = st.form_submit_button("食事を保存")
            if submit_meal:
                meal_data = {
                    "date": target_date_str,
                    "meal_type": m_type,
                    "food_name": f_name,
                    "calories": float(c_cal),
                    "protein": float(c_p),
                    "fat": float(c_f),
                    "carbs": float(c_c),
                    "alcohol_g": float(c_alc),
                    "is_eating_out": is_out,
                    "restaurant_name": r_name,
                    "dining_partners": d_partners,
                    "eating_out_comment": e_comment
                }
                save_meal_item(meal_data)
                st.success("食事ログを保存しました！")
                st.rerun()

    st.divider()

    st.subheader("🏃 3. 運動ログの入力")
    registered_ex = get_exercises_by_date(target_date_str)
    if registered_ex:
        st.markdown("**登録済みの運動:**")
        for e in registered_ex:
            col_e1, col_e2 = st.columns([4, 1])
            with col_e1:
                st.caption(f"・{e.get('exercise_name')} | {e.get('duration_min')}分 ({e.get('burned_calories',0)} kcal消費)")
            with col_e2:
                if st.button("削除", key=f"del_ex_{e['id']}"):
                    delete_exercise_item(e['id'])
                    st.rerun()

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("⚡ 傾斜ウォーキング 45分 (300kcal) をクイック登録"):
            ex_data = {
                "date": target_date_str,
                "exercise_name": "傾斜ウォーキング",
                "duration_min": 45.0,
                "burned_calories": 300.0
            }
            save_exercise_item(ex_data)
            st.success("傾斜ウォーキングを登録しました！")
            st.rerun()

    ex_text_input = st.text_input("🤖 AI自然言語入力 (例: 脚トレ60分と有酸素30分)", key="ex_text_input")
    if st.button("AI解析して運動登録"):
        if ex_text_input:
            with st.spinner("AI解析中..."):
                parsed_ex = parse_exercise_text_with_ai(ex_text_input)
                parsed_ex["date"] = target_date_str
                save_exercise_item(parsed_ex)
                st.success(f"追加しました: {parsed_ex.get('exercise_name')}")
                st.rerun()

    st.divider()

    st.subheader("📖 4. 本日のジャーナリング")
    current_journal = get_journal(target_date_str)
    note_input = st.text_area("振り返り・体調・気づき", value=current_journal.get("note", ""))
    
    if st.button("ジャーナリングを保存してAIフィードバックを取得"):
        with st.spinner("AIアドバイス生成中..."):
            fb = generate_journal_feedback(note_input, registered_meals, registered_ex, current_habits)
            save_journal(target_date_str, note_input, fb)
            st.success("保存完了しました！")
            st.rerun()

    if current_journal.get("ai_feedback"):
        st.info(f"🤖 **AIフィードバック:**\n\n{current_journal.get('ai_feedback')}")

    st.divider()

    st.subheader("⚙️ 5. 体組成データのCSVインポート")
    uploaded_file = st.file_uploader("体組成計CSVファイルをアップロード", type=["csv"])
    if uploaded_file is not None:
        try:
            df_upload = pd.read_csv(uploaded_file)
            st.dataframe(df_upload.head())
            if st.button("CSVデータをFirestoreに一括保存"):
                save_body_composition_batch(df_upload)
                st.success("体組成データを一括インポートしました！")
        except Exception as err:
            st.error(f"ファイル読み込みエラー: {err}")

# =========================================================
# TAB 2: 📊 日次サマリー＆KPI
# =========================================================
with tab2:
    summary_date = st.date_input("サマリー表示日", date.today(), key="summary_date_picker")
    s_date_str = summary_date.strftime("%Y-%m-%d")

    day_meals = get_meals_by_date(s_date_str)
    day_exercises = get_exercises_by_date(s_date_str)
    day_habits = get_daily_habits(s_date_str)

    total_cal = sum(m.get("calories", 0.0) for m in day_meals)
    total_p = sum(m.get("protein", 0.0) for m in day_meals)
    total_f = sum(m.get("fat", 0.0) for m in day_meals)
    total_c = sum(m.get("carbs", 0.0) for m in day_meals)
    total_burned = sum(e.get("burned_calories", 0.0) for e in day_exercises)

    st.subheader(f"📌 {s_date_str} のKPI達成度")
    
    kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
    kpi1.metric("摂取カロリー", f"{total_cal:.0f} kcal", f"目標: {current_goals['target_cal']:.0f}")
    kpi2.metric("P (タンパク質)", f"{total_p:.1f} g", f"目標: {current_goals['target_p']:.0f}g")
    kpi3.metric("F (脂質)", f"{total_f:.1f} g", f"目標: {current_goals['target_f']:.0f}g")
    kpi4.metric("C (炭水化物)", f"{total_c:.1f} g", f"目標: {current_goals['target_c']:.0f}g")
    kpi5.metric("消費カロリー", f"{total_burned:.0f} kcal")

    st.divider()
    st.subheader("🏋️ 習慣チェックイン状況")
    hc1, hc2, hc3 = st.columns(3)
    hc1.info(f"**運動:** {day_habits.get('gym', '未記録')}")
    hc2.info(f"**英語:** {day_habits.get('english', '未記録')}")
    hc3.info(f"**休肝日:** {day_habits.get('rest_day', '未記録')}")

    st.divider()
    st.subheader("🍕 食事明細・外食記録")
    if day_meals:
        for m in day_meals:
            badge = "🍺 外食" if m.get("is_eating_out") else "🏠 自食"
            st.markdown(f"##### {badge} [{m.get('meal_type')}] {m.get('food_name')}")
            st.text(f"カロリー: {m.get('calories')}kcal | P:{m.get('protein')}g F:{m.get('fat')}g C:{m.get('carbs')}g")
            if m.get("is_eating_out"):
                st.caption(f"📍 店名: {m.get('restaurant_name')} | 👥 同行者: {m.get('dining_partners')}")
                if m.get("eating_out_comment"):
                    st.caption(f"💬 メモ: {m.get('eating_out_comment')}")
            st.divider()
    else:
        st.write("食事記録がありません。")

# =========================================================
# TAB 3: 📈 習慣＆体組成の分析
# =========================================================
with tab3:
    st.subheader("📈 過去30日間の習慣達成内訳")
    
    end_d = date.today()
    start_d = end_d - timedelta(days=29)
    date_list = [(start_d + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(30)]

    habits_data = []
    for d_str in date_list:
        h = get_daily_habits(d_str)
        habits_data.append({
            "date": d_str,
            "gym": h.get("gym", "未記録"),
            "english": h.get("english", "未記録"),
            "rest_day": h.get("rest_day", "未記録")
        })
    
    df_habits = pd.DataFrame(habits_data)
    df_melted = df_habits.melt(id_vars=["date"], var_name="habit_type", value_name="status")
    
    fig_habit = px.bar(
        df_melted, 
        x="date", 
        color="status", 
        facet_row="habit_type",
        title="習慣化ステータス推移（過去30日）",
        color_discrete_map={
            "目標達成": "#2ecc71",
            "一応やった": "#f1c40f",
            "未実施": "#e74c3c",
            "未記録": "#95a5a6"
        }
    )
    st.plotly_chart(fig_habit, use_container_width=True)

    st.divider()
    st.subheader("🥗 過去7日間の栄養・PFC摂取量推移")

    start_7d = end_d - timedelta(days=6)
    date_list_7d = [(start_7d + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]

    pfc_data = []
    for d_str in date_list_7d:
        meals = get_meals_by_date(d_str)
        pfc_data.append({
            "date": d_str,
            "calories": sum(m.get("calories", 0.0) for m in meals),
            "protein": sum(m.get("protein", 0.0) for m in meals),
            "fat": sum(m.get("fat", 0.0) for m in meals),
            "carbs": sum(m.get("carbs", 0.0) for m in meals)
        })
    df_pfc = pd.DataFrame(pfc_data)

    fig_cal = px.bar(
        df_pfc, 
        x="date", 
        y="calories", 
        title="総摂取カロリー推移 (kcal)",
        labels={"calories": "カロリー (kcal)", "date": "日付"},
        color_discrete_sequence=["#3498db"]
    )
    fig_cal.add_hline(
        y=current_goals["target_cal"], 
        line_dash="dash", 
        line_color="red", 
        annotation_text=f"目標: {current_goals['target_cal']}kcal"
    )
    st.plotly_chart(fig_cal, use_container_width=True)

    col_p, col_f, col_c = st.columns(3)

    with col_p:
        fig_p = px.bar(
            df_pfc, 
            x="date", 
            y="protein", 
            title="タンパク質 (P) 推移",
            labels={"protein": "P (g)", "date": "日付"},
            color_discrete_sequence=["#e74c3c"]
        )
        fig_p.add_hline(
            y=current_goals["target_p"], 
            line_dash="dash", 
            line_color="black", 
            annotation_text=f"目標: {current_goals['target_p']}g"
        )
        st.plotly_chart(fig_p, use_container_width=True)

    with col_f:
        fig_f = px.bar(
            df_pfc, 
            x="date", 
            y="fat", 
            title="脂質 (F) 推移",
            labels={"fat": "F (g)", "date": "日付"},
            color_discrete_sequence=["#f39c12"]
        )
        fig_f.add_hline(
            y=current_goals["target_f"], 
            line_dash="dash", 
            line_color="black", 
            annotation_text=f"目標: {current_goals['target_f']}g"
        )
        st.plotly_chart(fig_f, use_container_width=True)

    with col_c:
        fig_c = px.bar(
            df_pfc, 
            x="date", 
            y="carbs", 
            title="炭水化物 (C) 推移",
            labels={"carbs": "C (g)", "date": "日付"},
            color_discrete_sequence=["#2ecc71"]
        )
        fig_c.add_hline(
            y=current_goals["target_c"], 
            line_dash="dash", 
            line_color="black", 
            annotation_text=f"目標: {current_goals['target_c']}g"
        )
        st.plotly_chart(fig_c, use_container_width=True)

    st.divider()
    st.subheader("⚖️ 体組成推移")
    
    body_docs = db.collection("body_composition").order_by("date").get()
    if body_docs:
        body_list = [d.to_dict() for d in body_docs]
        df_body = pd.DataFrame(body_list)
        
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            fig_w = px.line(df_body, x="date", y="weight", markers=True, title="体重推移 (kg)", labels={"weight": "体重 (kg)", "date": "日付"})
            st.plotly_chart(fig_w, use_container_width=True)
            
            fig_m = px.line(df_body, x="date", y="muscle_mass", markers=True, title="骨格筋量推移 (kg)", labels={"muscle_mass": "骨格筋量 (kg)", "date": "日付"})
            st.plotly_chart(fig_m, use_container_width=True)
            
        with col_b2:
            fig_fat = px.line(df_body, x="date", y="body_fat", markers=True, title="体脂肪率推移 (%)", labels={"body_fat": "体脂肪率 (%)", "date": "日付"})
            st.plotly_chart(fig_fat, use_container_width=True)
            
            fig_bmr = px.line(df_body, x="date", y="bmr", markers=True, title="基礎代謝推移 (kcal)", labels={"bmr": "基礎代謝 (kcal)", "date": "日付"})
            st.plotly_chart(fig_bmr, use_container_width=True)
    else:
        st.info("体組成データがまだ登録されていません。TAB 1からCSVをアップロードしてください。")

# =========================================================
# TAB 4: ⚙️ 設定
# =========================================================
with tab4:
    st.subheader("⚙️ アプリケーション設定")
    st.write("・**データベース**: Google Cloud Firestore")
    st.write("・**使用LLM**: Gemini 3.6 Flash (`google-genai` SDK)")
    st.write("・**デプロイ環境**: Streamlit Community Cloud")
    st.info("目標マクロの変更はサイドバーの「🎯 目標マクロ設定」をご利用ください。")
