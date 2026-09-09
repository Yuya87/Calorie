import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta, date
from google.oauth2 import service_account
from google.cloud import firestore
import json
from google import genai
from google.genai import types
import io

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
            if isinstance(secret_val, str):
                key_dict = json.loads(secret_val)
            else:
                key_dict = dict(secret_val)
            
            if "private_key" in key_dict:
                key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
                
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
    {{
      "meal_type": "朝食", // 発言内容や入力時間帯から「朝食」「昼食」「夕食」のいずれかを推測。特定できない場合は「不明」としてください
      "food_name": "品目名", 
      "calories": 数値, 
      "protein": 数値, 
      "fat": 数値, 
      "carbs": 数値, 
      "alcohol_g": 数値
    }}
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
    st.subheader("📅 記録対象日の選択")
    selected_date = st.date_input("入力・編集する日付", date.today(), key="main_date_input")
    selected_date_str = selected_date.strftime("%Y-%m-%d")

    # 既存データの取得
    exist_meals = fetch_daily_meals(selected_date_str)
    exist_exercises = fetch_daily_exercises(selected_date_str)
    exist_habit = fetch_daily_habit(selected_date_str)
    exist_journal = fetch_journal(selected_date_str)
    exist_body = fetch_body_comp(selected_date_str)

    st.divider()

    # 2. 習慣化チェックイン
    st.subheader("🏋️ 1. 習慣化チェックイン")
    habit_options = ["目標達成", "一応やった", "未実施", "未記録"]

    def get_habit_idx(val):
        return habit_options.index(val) if val in habit_options else 3

    with st.form("habit_input_form"):
        h_col1, h_col2, h_col3 = st.columns(3)
        with h_col1:
            gym_val = st.selectbox("🏃 運動", habit_options, index=get_habit_idx(exist_habit.get("gym", "未記録")))
        with h_col2:
            eng_val = st.selectbox("📚 英語学習", habit_options, index=get_habit_idx(exist_habit.get("english", "未記録")))
        with h_col3:
            rest_val = st.selectbox("🍺 休肝日", habit_options, index=get_habit_idx(exist_habit.get("rest_day", "未記録")))
            
        h_memo = st.text_input("習慣メモ", value=exist_habit.get("memo", ""), placeholder="例: 脚トレ実施 / 瞬間英作文20分")
        if st.form_submit_button("習慣化データを保存"):
            save_daily_habit(selected_date_str, gym_val, eng_val, rest_val, h_memo)
            st.success("習慣化データを保存しました！")
            st.rerun()

    st.divider()

    # 3. 食事ログ入力
    st.subheader("🥗 2. 食事ログの入力")
    if exist_meals:
        with st.expander(f"📋 登録済みの食事 ({len(exist_meals)} 件)", expanded=True):
            for idx, m in enumerate(exist_meals, 1):
                out_info = f" 【外食: {m.get('restaurant_name', '')}】" if m.get("is_eating_out") else ""
                meal_type = m.get("meal_type", "不明")
                st.write(f"{idx}. [{meal_type}] **{m.get('food_name')}** - {m.get('calories')}kcal (P:{m.get('protein')}g F:{m.get('fat')}g C:{m.get('carbs')}g){out_info}")

    with st.form("meal_ai_form"):
        meal_text = st.text_area("食事内容（時間帯の指定がない場合は現在の時間からAIが推測します）", placeholder="例: 昼食に丸の内のうなぎ屋で特上うな重を食べた。")
        is_out = st.checkbox("🍔 外食・会食として記録する")
        
        rest_name, partners, out_comment = "", "", ""
        if is_out:
            m_col1, m_col2 = st.columns(2)
            rest_name = m_col1.text_input("店名・場所")
            partners = m_col2.text_input("誰と（同行者）")
            out_comment = st.text_input("外食に関するメモ・評価")

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

    st.markdown("**🔥 傾斜ウォーキングのワンタップ記録**")
    with st.form("incline_walking_form"):
        walk_col1, walk_col2 = st.columns([3, 1])
        with walk_col1:
            walk_min = st.number_input("実施時間 (分)", min_value=1, value=30, step=5)
        with walk_col2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.form_submit_button("ワンタップ記録"):
                burn = walk_min * 7.5
                if db:
                    db.collection("exercises").add({
                        "date": selected_date_str,
                        "exercise_name": "傾斜ウォーキング",
                        "duration_min": float(walk_min),
                        "burned_calories": float(burn),
                        "created_at": firestore.SERVER_TIMESTAMP
                    })
                st.success("傾斜ウォーキングを記録しました！")
                st.rerun()

    st.markdown("**🤖 その他の運動記録（AI解析）**")
    with st.form("exercise_ai_form"):
        ex_text = st.text_area("その他の運動内容", placeholder="例: ベンチプレス 30分")
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
            height=100
        )
        if st.form_submit_button("ジャーナルを保存"):
            save_journal(selected_date_str, j_note, exist_journal.get("ai_feedback", "") if exist_journal else "")
            st.success("ジャーナルを保存しました！")
            st.rerun()

    st.divider()

    # 6. 体組成データのCSVインポート
    st.subheader("⚙️ 5. 体組成データの入力 (CSV一括アップロード)")
    st.info("※対応形式: ご提供いただいたCSVフォーマット（測定日、体重(kg)、体脂肪(%)、骨格筋量(kg)、基礎代謝(kcal) が含まれるデータ）")
    
    uploaded_file = st.file_uploader("体組成計のCSVデータをアップロード", type=["csv"])
    if uploaded_file is not None:
        if st.button("CSVデータをインポート"):
            try:
                # CSV読み込みと日付の整形
                df = pd.read_csv(uploaded_file)
                if "測定日" in df.columns and "体重(kg)" in df.columns:
                    df['date_str'] = pd.to_datetime(df['測定日']).dt.strftime('%Y-%m-%d')
                    df['datetime'] = pd.to_datetime(df['測定日'])
                    
                    # 同一日に複数データがある場合は時系列ソートして最新（最後）のデータを優先
                    df = df.sort_values('datetime')
                    df_daily = df.drop_duplicates(subset=['date_str'], keep='last')
                    
                    if db:
                        batch = db.batch()
                        count = 0
                        for _, row in df_daily.iterrows():
                            doc_ref = db.collection("body_composition").document(row['date_str'])
                            batch.set(doc_ref, {
                                "date": row['date_str'],
                                "weight": float(row['体重(kg)']),
                                "body_fat": float(row['体脂肪(%)']) if '体脂肪(%)' in row else 0.0,
                                "muscle_mass": float(row['骨格筋量(kg)']) if '骨格筋量(kg)' in row else 0.0,
                                "bmr": float(row['基礎代謝(kcal)']) if '基礎代謝(kcal)' in row else 0.0,
                                "updated_at": firestore.SERVER_TIMESTAMP
                            }, merge=True)
                            count += 1
                        batch.commit()
                        st.success(f"{count}日分の体組成データをFirestoreに一括登録しました！")
                else:
                    st.error("CSVの形式が異なります。対応するカラム（測定日、体重(kg) 等）が含まれるデータをアップロードしてください。")
            except Exception as e:
                st.error(f"インポート処理中にエラーが発生しました: {e}")

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
    
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("カロリー", f"{int(tot_cal)} kcal", f"{int(tot_cal - goals['target_cal'])} kcal")
    col2.metric("P (タンパク質)", f"{tot_p:.1f} g", f"{tot_p - goals['target_p']:.1f} g")
    col3.metric("F (脂質)", f"{tot_f:.1f} g", f"{tot_f - goals['target_f']:.1f} g")
    col4.metric("C (炭水化物)", f"{tot_c:.1f} g", f"{tot_c - goals['target_c']:.1f} g")
    col5.metric("運動消費", f"{int(tot_burn)} kcal", f"{len(exercises)} 件")

    st.divider()

    st.markdown("##### 🏋️ 本日の習慣達成ステータス")
    hc1, hc2, hc3 = st.columns(3)
    hc1.info(f"**運動**: {habit.get('gym', '未記録')}")
    hc2.info(f"**英語学習**: {habit.get('english', '未記録')}")
    hc3.info(f"**休肝日**: {habit.get('rest_day', '未記録')}")

    st.divider()

    st.markdown("##### 🥗 食事明細＆外食記録")
    if meals:
        for m in meals:
            m_type = m.get("meal_type", "不明")
            if m.get("is_eating_out"):
                st.warning(f"🍺 **【外食 / {m_type}】{m.get('food_name')}** ({m.get('calories')} kcal)\n"
                           f"- 店名: {m.get('restaurant_name', '未入力')} / 同行者: {m.get('dining_partners', '未入力')}\n"
                           f"- メモ: {m.get('eating_out_comment', 'なし')}")
            else:
                st.write(f"🍽️ **[{m_type}] {m.get('food_name')}** - {m.get('calories')} kcal (P:{m.get('protein')}g, F:{m.get('fat')}g, C:{m.get('carbs')}g)")
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
        for item, label in [("gym", "運動"), ("english", "英語学習"), ("rest_day", "休肝日")]:
            if item in df_h.columns:
                counts = df_h[item].value_counts()
                for status in ["目標達成", "一応やった", "未実施"]:
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
                "一応やった": "#d97706",
                "未実施": "#da3633"
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
