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
            secret_val = st.secrets["gcp_service_account"]
            # dict/AttrDictか文字列かで処理を分岐
            if isinstance(secret_val, str):
                key_dict = json.loads(secret_val)
            else:
                key_dict = dict(secret_val)
                
            creds = service_account.Credentials.from_service_account_info(key_dict)
            return firestore.Client(credentials=creds, project=key_dict.get("project_id"))
        else:
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
# 3. データ操作ヘルパー関数 (Firestore)
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

# 習慣トラッカー関数
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
# 4. AI解析ロジック (Gemini 3.6 Flash)
# ---------------------------------------------------------
def parse_and_save_meal(user_text, target_date_str, is_eating_out=False, restaurant_name="", dining_partners="", eating_out_comment=""):
    if not ai_client:
        return "AIクライアントが初期化されていません。"

    prompt = f"""
あなたは優しく優秀なパーソナルボディメイクコーチです。
ユーザーの発言から「食事」に関するデータを抽出し、以下のJSON形式厳守で出力してください。

対象日付: {target_date_str}

【抽出フォーマット】
{{
  "meals": [
    {{"food_name": "品目名", "calories": 数値, "protein": 数値, "fat": 数値, "carbs": 数値, "alcohol_g": 数値}}
  ],
  "advice": "ユーザーへの温かい励ましと栄養アドバイス（100文字程度）"
}}

※食事データの該当がない場合は空配列 `[]` としてください。
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
        
        if db:
            for m in data.get("meals", []):
                m["date"] = target_date_str
                m["is_eating_out"] = is_eating_out
                m["restaurant_name"] = restaurant_name if is_eating_out else ""
                m["dining_partners"] = dining_partners if is_eating_out else ""
                m["eating_out_comment"] = eating_out_comment if is_eating_out else ""
                m["created_at"] = firestore.SERVER_TIMESTAMP
                db.collection("meals").add(m)
                
        return data.get("advice", "食事記録を保存しました！")
    except Exception as e:
        return f"解析エラーが発生しました: {e}"

def parse_and_save_exercise(user_text, target_date_str):
    if not ai_client:
        return "AIクライアントが初期化されていません。"

    prompt = f"""
ユーザーの発言から「運動」に関するデータを抽出し、以下のJSON形式厳守で出力してください。

【抽出フォーマット】
{{
  "exercises": [
    {{"exercise_name": "種目名", "duration_min": 分数数値, "burned_calories": 数値}}
  ],
  "advice": "運動に対する短い労いのコメント（50文字程度）"
}}

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
        
        if db:
            for e in data.get("exercises", []):
                e["date"] = target_date_str
                e["created_at"] = firestore.SERVER_TIMESTAMP
                db.collection("exercises").add(e)
                
        return data.get("advice", "運動記録を保存しました！")
    except Exception as e:
        return f"解析エラーが発生しました: {e}"

# ---------------------------------------------------------
# 5. メインUI構造 (Streamlit)
# ---------------------------------------------------------
st.title("💪 AI Body Make & Habit Tracker")

# サイドバー: 目標設定
with st.sidebar:
    st.header("⚙️ システム設定")
    st.subheader("🎯 目標マクロ設定")
    current_goals = fetch_user_goals()
    with st.form("goals_form_side"):
        g_cal = st.number_input("目標カロリー (kcal)", value=int(current_goals.get("target_cal", 2200)))
        g_p = st.number_input("目標 P (g)", value=int(current_goals.get("target_p", 160)))
        g_f = st.number_input("目標 F (g)", value=int(current_goals.get("target_f", 50)))
        g_c = st.number_input("目標 C (g)", value=int(current_goals.get("target_c", 250)))
        if st.form_submit_button("目標を更新"):
            save_user_goals(g_cal, g_p, g_f, g_c)
            st.success("目標を更新しました！")

# タブ定義
tab1, tab2, tab3, tab4 = st.tabs([
    "📝 本日のデータ入力", 
    "📊 日次サマリー＆KPI", 
    "📈 習慣＆体組成の分析", 
    "⚙️ 設定"
])

# ---------------------------------------------------------
# TAB 1: 本日のデータ入力 (メイン入力画面)
# ---------------------------------------------------------
with tab1:
    # 1. 最上部: 日付選択 & ステータス表示
    st.subheader("📅 記録対象日の選択")
    date_col1, date_col2 = st.columns([1, 2])
    with date_col1:
        selected_date = st.date_input("入力・編集する日付", date.today(), key="main_date_input")
        selected_date_str = selected_date.strftime("%Y-%m-%d")

    # 既存データの取得（ステータス確認用）
    exist_meals = fetch_daily_meals(selected_date_str)
    exist_exercises = fetch_daily_exercises(selected_date_str)
    exist_habit = fetch_daily_habit(selected_date_str)
    exist_journal = fetch_journal(selected_date_str)
    exist_body = fetch_body_comp(selected_date_str)

    # ステータスパネル表示
    with date_col2:
        st.markdown("**📌 本日の登録状況ステータス**")
        s_col1, s_col2, s_col3, s_col4, s_col5 = st.columns(5)
        
        has_habit = exist_habit.get("gym") != "未記録" or exist_habit.get("english") != "未記録" or exist_habit.get("rest_day") != "未記録"
        s_col1.markdown(f"**習慣**: {'✅ 記録済' if has_habit else '⚠️ 未入力'}")
        s_col2.markdown(f"**食事**: {'✅ 記録済' if len(exist_meals) > 0 else '⚠️ 未入力'}")
        s_col3.markdown(f"**運動**: {'✅ 記録済' if len(exist_exercises) > 0 else '⚠️ 未入力'}")
        s_col4.markdown(f"**ジャーナル**: {'✅ 記録済' if exist_journal and exist_journal.get('note') else '⚠️ 未入力'}")
        s_col5.markdown(f"**体組成**: {'✅ 記録済' if exist_body and exist_body.get('weight') else '⚠️ 未入力'}")

    st.divider()

    # 2. 習慣化チェックイン
    st.subheader("🏋️ 1. 習慣化チェックイン")
    habit_options = ["目標達成", "できてないけど一応やった", "やらなかった", "未記録"]

    with st.form("habit_input_form"):
        h_col1, h_col2, h_col3 = st.columns(3)
        with h_col1:
            gym_val = st.selectbox("🏋️ ジム / 筋トレ", habit_options, index=habit_options.index(exist_habit.get("gym", "未記録")))
        with h_col2:
            eng_val = st.selectbox("📚 英語学習", habit_options, index=habit_options.index(exist_habit.get("english", "未記録")))
        with h_col3:
            rest_val = st.selectbox("🍺/🚬 休肝日・休煙日", habit_options, index=habit_options.index(exist_habit.get("rest_day", "未記録")))
            
        h_memo = st.text_input("習慣メモ", value=exist_habit.get("memo", ""), placeholder="例: 脚トレ実施 / 瞬間英作文20分")
        if st.form_submit_button("習慣化データを保存"):
            save_daily_habit(selected_date_str, gym_val, eng_val, rest_val, h_memo)
            st.success("習慣化データを保存しました！")
            st.rerun()

    st.divider()

    # 3. 食事ログ入力（AI入力 ＋ 外食オプション）
    st.subheader("🥗 2. 食事ログの入力")
    
    # 登録済み食事データの表示
    if exist_meals:
        with st.expander(f"📋 登録済みの食事 ({len(exist_meals)} 件)", expanded=True):
            for idx, m in enumerate(exist_meals, 1):
                out_info = f" 【外食: {m.get('restaurant_name', '')} / 同行: {m.get('dining_partners', '')}】" if m.get("is_eating_out") else ""
                st.write(f"{idx}. **{m.get('food_name')}** - {m.get('calories')}kcal (P:{m.get('protein')}g F:{m.get('fat')}g C:{m.get('carbs')}g){out_info}")

    with st.form("meal_ai_form"):
        meal_text = st.text_area("食事内容（AIが栄養素を解析します）", placeholder="例: 昼食に丸の内のうなぎ屋で特上うな重を食べた。炭水化物多め。")
        
        # 外食フラグ & 詳細項目
        is_out = st.checkbox("🍔 外食・会食として記録する")
        
        rest_name, partners, out_comment = "", "", ""
        if is_out:
            m_col1, m_col2 = st.columns(2)
            rest_name = m_col1.text_input("店名・場所", placeholder="例: 叙々苑 六本木店")
            partners = m_col2.text_input("誰と（同行者）", placeholder="例: 取引先担当者、チームメンバー")
            out_comment = st.text_input("外食に関するメモ・評価", placeholder="例: ビジネス会食。アルコールは控えめに抑えた。")

        if st.form_submit_button("AIで解析して食事を保存"):
            if meal_text.strip():
                with st.spinner("AIが栄養素を解析中..."):
                    adv = parse_and_save_meal(meal_text, selected_date_str, is_out, rest_name, partners, out_comment)
                    st.success(f"保存完了: {adv}")
                    st.rerun()
            else:
                st.warning("食事内容を入力してください。")

    st.divider()

    # 4. 運動ログ入力
    st.subheader("🏃 3. 運動ログの入力")
    if exist_exercises:
        with st.expander(f"📋 登録済みの運動 ({len(exist_exercises)} 件)", expanded=True):
            for idx, e in enumerate(exist_exercises, 1):
                st.write(f"{idx}. **{e.get('exercise_name')}** - {e.get('duration_min')}分 ({e.get('burned_calories')} kcal消費)")

    with st.form("exercise_ai_form"):
        ex_text = st.text_area("運動内容", placeholder="例: 10kmランニング 50分、ベンチプレス 30分")
        if st.form_submit_button("AIで解析して運動を保存"):
            if ex_text.strip():
                with st.spinner("AIが消費カロリーを解析中..."):
                    adv = parse_and_save_exercise(ex_text, selected_date_str)
                    st.success(f"保存完了: {adv}")
                    st.rerun()
            else:
                st.warning("運動内容を入力してください。")

    st.divider()

    # 5. ジャーナリング入力
    st.subheader("📖 4. 本日のジャーナリング（振り返り）")
    with st.form("journal_input_form"):
        j_note = st.text_area(
            "振り返り・体調・気づき", 
            value=exist_journal.get("note", "") if exist_journal else "",
            height=100,
            placeholder="今日の体調、メンタル、気づいたこと..."
        )
        if st.form_submit_button("ジャーナルを保存"):
            save_journal(selected_date_str, j_note, exist_journal.get("ai_feedback", "") if exist_journal else "")
            st.success("ジャーナルを保存しました！")
            st.rerun()

    st.divider()

    # 6. 体組成データの入力
    st.subheader("⚙️ 5. 体組成データの入力")
    with st.form("body_comp_input_form"):
        b_col1, b_col2 = st.columns(2)
        w = b_col1.number_input("体重 (kg)", value=float(exist_body.get("weight", 70.0)) if exist_body else 70.0, step=0.1)
        bf = b_col2.number_input("体脂肪率 (%)", value=float(exist_body.get("body_fat", 18.0)) if exist_body else 18.0, step=0.1)
        mm = b_col1.number_input("筋肉量 (kg)", value=float(exist_body.get("muscle_mass", 55.0)) if exist_body else 55.0, step=0.1)
        bmr = b_col2.number_input("基礎代謝 (kcal)", value=float(exist_body.get("bmr", 1600.0)) if exist_body else 1600.0, step=10.0)
        
        if st.form_submit_button("体組成データを保存"):
            save_body_comp(selected_date_str, w, bf, mm, bmr)
            st.success("体組成データを保存しました！")
            st.rerun()

# ---------------------------------------------------------
# TAB 2: 日次サマリー ＆ KPI (閲覧・確認)
# ---------------------------------------------------------
with tab2:
    st.subheader(f"📊 日次サマリー ({selected_date_str})")
    
    meals = fetch_daily_meals(selected_date_str)
    exercises = fetch_daily_exercises(selected_date_str)
    goals = fetch_user_goals()
    habit = fetch_daily_habit(selected_date_str)
    
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

    # 習慣達成表示
    st.markdown("##### 🏋️ 本日の習慣達成ステータス")
    hc1, hc2, hc3 = st.columns(3)
    hc1.info(f"**ジム/筋トレ**: {habit.get('gym', '未記録')}")
    hc2.info(f"**英語学習**: {habit.get('english', '未記録')}")
    hc3.info(f"**休肝・休煙日**: {habit.get('rest_day', '未記録')}")

    st.divider()

    # 食事明細（外食ハイライト）
    st.markdown("##### 🥗 食事明細＆外食記録")
    if meals:
        for m in meals:
            if m.get("is_eating_out"):
                st.warning(f"🍺 **【外食】{m.get('food_name')}** ({m.get('calories')} kcal)\n"
                           f"- 店名: {m.get('restaurant_name', '未入力')} / 同行者: {m.get('dining_partners', '未入力')}\n"
                           f"- メモ: {m.get('eating_out_comment', 'なし')}")
            else:
                st.write(f"🍽️ **{m.get('food_name')}** - {m.get('calories')} kcal (P:{m.get('protein')}g, F:{m.get('fat')}g, C:{m.get('carbs')}g)")
    else:
        st.caption("食事データはありません。")

# ---------------------------------------------------------
# TAB 3: 履歴 ＆ 習慣化分析
# ---------------------------------------------------------
with tab3:
    st.subheader("📈 習慣化 ＆ 体組成データの分析")
    
    st.markdown("### 🗓️ 過去30日間の習慣達成分析")
    end_date_str = date.today().strftime("%Y-%m-%d")
    start_30d_str = (date.today() - timedelta(days=29)).strftime("%Y-%m-%d")
    
    habits_30d = fetch_habits_range(start_30d_str, end_date_str)
    
    if habits_30d:
        df_h = pd.DataFrame(habits_30d)
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
        st.info("過去30日間の習慣記録データが集まると、ここにグラフが表示されます。")

# ---------------------------------------------------------
# TAB 4: 設定
# ---------------------------------------------------------
with tab4:
    st.subheader("⚙️ アプリ・目標設定")
    st.write("サイドバーから目標マクロ（カロリー、PFC）を変更・保存できます。")
