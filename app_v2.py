import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta, date
from google.oauth2 import service_account
from google.cloud import firestore
import json
from google import genai
from google.genai import types

# ---------------------------------------------------------
# 1. ページ初期設定
# ---------------------------------------------------------
st.set_page_config(
    page_title="AI Body Make & Habit Tracker",
    page_icon="💪",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------------------------------------------------
# 2. クラウドサービス初期化 (Firestore & Gemini)
# ---------------------------------------------------------
@st.cache_resource
def init_firestore():
    """GCP Firestore クライアントの初期化"""
    try:
        if "gcp_service_account" in st.secrets:
            key_dict = json.loads(st.secrets["gcp_service_account"])
            creds = service_account.Credentials.from_service_account_info(key_dict)
            return firestore.Client(credentials=creds, project=key_dict.get("project_id"))
        else:
            # ローカル等で環境変数が用意されている場合のフォールバック
            return firestore.Client()
    except Exception as e:
        st.error(f"Firestore初期化エラー: {e}")
        return None

db = init_firestore()

def get_gemini_client():
    """Google GenAI SDK (gemini-3.6-flash) クライアントの初期化"""
    try:
        api_key = st.secrets.get("GEMINI_API_KEY", None)
        if api_key:
            return genai.Client(api_key=api_key)
        return genai.Client()
    except Exception as e:
        st.error(f"Gemini API初期化エラー: {e}")
        return None

ai_client = get_gemini_client()

# ---------------------------------------------------------
# 3. データ操作ヘパー関数 (Firestore)
# ---------------------------------------------------------
def fetch_user_goals():
    if not db:
        return {"target_cal": 2200, "target_p": 160, "target_f": 50, "target_c": 250}
    docs = db.collection("user_goals").order_by("updated_at", direction=firestore.Query.DESCENDING).limit(1).get()
    for doc in docs:
        return doc.to_dict()
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

def fetch_daily_meals(selected_date_str):
    if not db:
        return []
    docs = db.collection("meals").where("date", "==", selected_date_str).get()
    return [d.to_dict() for d in docs]

def fetch_daily_exercises(selected_date_str):
    if not db:
        return []
    docs = db.collection("exercises").where("date", "==", selected_date_str).get()
    return [d.to_dict() for d in docs]

def fetch_body_comp(selected_date_str):
    if not db:
        return None
    doc = db.collection("body_composition").document(selected_date_str).get()
    return doc.to_dict() if doc.exists else None

def save_body_comp(selected_date_str, weight, body_fat, muscle_mass, bmr):
    if db:
        db.collection("body_composition").document(selected_date_str).set({
            "date": selected_date_str,
            "weight": float(weight),
            "body_fat": float(body_fat),
            "muscle_mass": float(muscle_mass),
            "bmr": float(bmr),
            "updated_at": firestore.SERVER_TIMESTAMP
        }, merge=True)

def fetch_journal(selected_date_str):
    if not db:
        return None
    doc = db.collection("journals").document(selected_date_str).get()
    return doc.to_dict() if doc.exists else None

def save_journal(selected_date_str, note, ai_feedback=""):
    if db:
        db.collection("journals").document(selected_date_str).set({
            "date": selected_date_str,
            "note": note,
            "ai_feedback": ai_feedback,
            "updated_at": firestore.SERVER_TIMESTAMP
        }, merge=True)

# --- 習慣トラッカー関数 ---
def fetch_daily_habit(selected_date_str):
    if not db:
        return {"gym": "未記録", "english": "未記録", "rest_day": "未記録", "memo": ""}
    doc = db.collection("daily_habits").document(selected_date_str).get()
    if doc.exists:
        return doc.to_dict()
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
    docs = db.collection("daily_habits")\
        .where("date", ">=", start_date_str)\
        .where("date", "<=", end_date_str).get()
    return [d.to_dict() for d in docs]

# ---------------------------------------------------------
# 4. AI処理ロジック (Gemini 3.6 Flash)
# ---------------------------------------------------------
def parse_and_save_log(user_text, target_date_str):
    if not ai_client:
        return "AIクライアントが初期化されていません。"

    prompt = f"""
あなたは優しく優秀なパーソナルボディメイクコーチです。
ユーザーの発言から「食事」「運動」に関するデータを抽出し、以下のJSON形式厳守で出力してください。

対象日付: {target_date_str}

【抽出フォーマット】
{{
  "meals": [
    {{"food_name": "品目名", "calories": 数値, "protein": 数値, "fat": 数値, "carbs": 数値, "alcohol_g": 数値}}
  ],
  "exercises": [
    {{"exercise_name": "種目名", "duration_min": 分数数値, "burned_calories": 数値}}
  ],
  "advice": "ユーザーへの温かい励ましとアドバイス（100文字程度）"
}}

※該当がないデータ配列は空 `[]` としてください。
※数値は推定でかまいません。

ユーザーの発言:
{user_text}
"""
    try:
        response = ai_client.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        data = json.loads(response.text)
        
        # Firestoreへの保存処理
        if db:
            for m in data.get("meals", []):
                m["date"] = target_date_str
                m["created_at"] = firestore.SERVER_TIMESTAMP
                db.collection("meals").add(m)
            
            for e in data.get("exercises", []):
                e["date"] = target_date_str
                e["created_at"] = firestore.SERVER_TIMESTAMP
                db.collection("exercises").add(e)
                
        return data.get("advice", "記録を登録しました！")
    except Exception as e:
        return f"解析エラーが発生しました: {e}"

# ---------------------------------------------------------
# 5. メインUI構造 (Streamlit)
# ---------------------------------------------------------
st.title("💪 AI Body Make & Habit Tracker")

# サイドバー: 日付選択 & 目標設定
with st.sidebar:
    st.header("📅 設定 & 操作")
    selected_date = st.date_input("記録対象日", date.today())
    selected_date_str = selected_date.strftime("%Y-%m-%d")
    
    st.divider()
    st.subheader("🎯 目標マクロ設定")
    current_goals = fetch_user_goals()
    with st.form("goals_form"):
        g_cal = st.number_input("目標カロリー (kcal)", value=int(current_goals.get("target_cal", 2200)))
        g_p = st.number_input("目標 P (g)", value=int(current_goals.get("target_p", 160)))
        g_f = st.number_input("目標 F (g)", value=int(current_goals.get("target_f", 50)))
        g_c = st.number_input("目標 C (g)", value=int(current_goals.get("target_c", 250)))
        if st.form_submit_button("目標を更新"):
            save_user_goals(g_cal, g_p, g_f, g_c)
            st.success("目標を更新しました！")

# メインタブの構成
tab1, tab2, tab3, tab4 = st.tabs([
    "💬 AI対話・食事運動入力", 
    "📊 日次サマリー＆習慣・ジャーナル", 
    "📈 履歴＆習慣化分析", 
    "⚙️ 体組成・設定"
])

# ---------------------------------------------------------
# TAB 1: AI対話・食事運動入力
# ---------------------------------------------------------
with tab1:
    st.subheader(f"💬 本日の対話・記録入力 ({selected_date_str})")
    st.caption("食べたものや行った運動を自然な言葉で入力してください。AIが自動で成分や消費カロリーを抽出・保存します。")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if user_input := st.chat_input("例: 朝食に胸肉150gとブロッコリーを食べた。夜は10kmランニング。"):
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            with st.spinner("AIがログを解析中..."):
                advice = parse_and_save_log(user_input, selected_date_str)
                st.markdown(advice)
                st.session_state.messages.append({"role": "assistant", "content": advice})

# ---------------------------------------------------------
# TAB 2: 日次サマリー ＆ 習慣・ジャーナル
# ---------------------------------------------------------
with tab2:
    st.subheader(f"📊 日次サマリー ({selected_date_str})")
    
    # 1. 栄養・運動データ計算
    meals = fetch_daily_meals(selected_date_str)
    exercises = fetch_daily_exercises(selected_date_str)
    goals = fetch_user_goals()
    
    tot_cal = sum(m.get("calories", 0) for m in meals)
    tot_p = sum(m.get("protein", 0) for m in meals)
    tot_f = sum(m.get("fat", 0) for m in meals)
    tot_c = sum(m.get("carbs", 0) for m in meals)
    tot_burn = sum(e.get("burned_calories", 0) for e in exercises)
    
    # KPI表示
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("カロリー", f"{int(tot_cal)} kcal", f"{int(tot_cal - goals['target_cal'])} kcal")
    col2.metric("P (タンパク質)", f"{tot_p:.1f} g", f"{tot_p - goals['target_p']:.1f} g")
    col3.metric("F (脂質)", f"{tot_f:.1f} g", f"{tot_f - goals['target_f']:.1f} g")
    col4.metric("C (炭水化物)", f"{tot_c:.1f} g", f"{tot_c - goals['target_c']:.1f} g")
    col5.metric("運動消費", f"{int(tot_burn)} kcal", f"{len(exercises)} 件")

    st.divider()

    # 2. 習慣化チェックイン セクション (新規追加)
    st.subheader("🏋️ 習慣化チェックイン")
    st.caption("今日の習慣達成状況を選択して更新してください。")

    habit_data = fetch_daily_habit(selected_date_str)
    habit_options = ["目標達成", "できてないけど一応やった", "やらなかった", "未記録"]

    with st.form("habit_checkin_form"):
        h_col1, h_col2, h_col3 = st.columns(3)
        
        with h_col1:
            gym_val = st.selectbox(
                "🏋️ ジム / 筋トレ", 
                options=habit_options, 
                index=habit_options.index(habit_data.get("gym", "未記録"))
            )
        with h_col2:
            eng_val = st.selectbox(
                "📚 英語学習", 
                options=habit_options, 
                index=habit_options.index(habit_data.get("english", "未記録"))
            )
        with h_col3:
            rest_val = st.selectbox(
                "🍺/🚬 休肝日・休煙日", 
                options=habit_options, 
                index=habit_options.index(habit_data.get("rest_day", "未記録"))
            )
        
        habit_memo = st.text_input("習慣化メモ（例: 脚トレ実施 / 瞬間英作文20分）", value=habit_data.get("memo", ""))
        
        if st.form_submit_button("習慣化チェックインを保存"):
            save_daily_habit(selected_date_str, gym_val, eng_val, rest_val, habit_memo)
            st.success("習慣化データを保存しました！")
            st.rerun()

    # 直近7日間の週間習慣達成度サマリー
    st.markdown("##### 🗓️ 直近7日間の習慣達成サマリー")
    start_7d = (selected_date - timedelta(days=6)).strftime("%Y-%m-%d")
    recent_habits = fetch_habits_range(start_7d, selected_date_str)
    
    if recent_habits:
        df_rec = pd.DataFrame(recent_habits)
        q_col1, q_col2, q_col3 = st.columns(3)
        
        for idx, (col, key, label) in enumerate([
            (q_col1, "gym", "🏋️ ジム"), 
            (q_col2, "english", "📚 英語"), 
            (q_col3, "rest_day", "🍺 休肝/休煙")
        ]):
            if key in df_rec.columns:
                achieved_cnt = (df_rec[key] == "目標達成").sum()
                partial_cnt = (df_rec[key] == "できてないけど一応やった").sum()
                col.info(f"**{label}**: 達成 {achieved_cnt}/7日 (一部達成: {partial_cnt}日)")
    else:
        st.caption("過去7日間の習慣記録はまだありません。")

    st.divider()

    # 3. 振り返り・ジャーナリング セクション
    st.subheader("📖 本日のジャーナリング")
    current_journal = fetch_journal(selected_date_str) or {}
    
    with st.form("journal_form"):
        j_note = st.text_area(
            "本日の振り返り・体調・メンタルメモ", 
            value=current_journal.get("note", ""),
            height=100,
            placeholder="今日のコンディションや反省点、気づいたことを自由に入力..."
        )
        if st.form_submit_button("ジャーナルを保存"):
            save_journal(selected_date_str, j_note, current_journal.get("ai_feedback", ""))
            st.success("ジャーナルを保存しました！")

# ---------------------------------------------------------
# TAB 3: 履歴 ＆ 習慣化分析
# ---------------------------------------------------------
with tab3:
    st.subheader("📈 習慣化 ＆ 体組成データの分析")
    
    # 習慣化分析（直近30日間）
    st.markdown("### 🗓️ 過去30日間の習慣達成分析")
    end_date_str = date.today().strftime("%Y-%m-%d")
    start_30d_str = (date.today() - timedelta(days=29)).strftime("%Y-%m-%d")
    
    habits_30d = fetch_habits_range(start_30d_str, end_date_str)
    
    if habits_30d:
        df_h = pd.DataFrame(habits_30d)
        
        # 内訳カウントグラフ
        chart_data = []
        for item, label in [("gym", "ジム/筋トレ"), ("english", "英語学習"), ("rest_day", "休肝・休煙")]:
            if item in df_h.columns:
                counts = df_h[item].value_counts()
                for status in ["目標達成", "できてないけど一応やった", "やらなかった"]:
                    chart_data.append({
                        "習慣": label,
                        "ステータス": status,
                        "日数": counts.get(status, 0)
                    })
        
        df_chart = pd.DataFrame(chart_data)
        fig_habits = px.bar(
            df_chart, 
            x="習慣", 
            y="日数", 
            color="ステータス", 
            title="過去30日間の習慣達成内訳",
            color_discrete_map={
                "目標達成": "#238636",
                "できてないけど一応やった": "#d97706",
                "やらなかった": "#da3633"
            },
            barmode="stack"
        )
        st.plotly_chart(fig_habits, use_container_width=True)
    else:
        st.info("過去30日間の習慣記録データが集まると、ここにグラフィカルな分析が表示されます。")

# ---------------------------------------------------------
# TAB 4: 体組成・設定
# ---------------------------------------------------------
with tab4:
    st.subheader(f"⚙️ 体組成データ登録 ({selected_date_str})")
    
    comp = fetch_body_comp(selected_date_str) or {}
    
    with st.form("body_comp_form"):
        c_col1, c_col2 = st.columns(2)
        w = c_col1.number_input("体重 (kg)", value=float(comp.get("weight", 70.0)), step=0.1)
        bf = c_col2.number_input("体脂肪率 (%)", value=float(comp.get("body_fat", 18.0)), step=0.1)
        mm = c_col1.number_input("筋肉量 (kg)", value=float(comp.get("muscle_mass", 55.0)), step=0.1)
        bmr = c_col2.number_input("基礎代謝 (kcal)", value=float(comp.get("bmr", 1600.0)), step=10.0)
        
        if st.form_submit_button("体組成データを保存"):
            save_body_comp(selected_date_str, w, bf, mm, bmr)
            st.success("体組成データを保存しました！")
