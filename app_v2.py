import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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

# 曜日表記のヘルパー
WEEKDAYS_JP = ["月", "火", "水", "木", "金", "土", "日"]
def format_date_with_weekday(d_val):
    if isinstance(d_val, str):
        try:
            d_val = datetime.strptime(d_val, "%Y-%m-%d").date()
        except Exception:
            return d_val
    return f"{d_val.strftime('%Y-%m-%d')} ({WEEKDAYS_JP[d_val.weekday()]})"

# 食事ソート用ロジック（朝食 -> 昼食 -> 夕食 -> 間食 -> 不明）
MEAL_ORDER_MAP = {"朝食": 0, "昼食": 1, "夕食": 2, "間食": 3, "不明": 4}
def sort_meals(meal_list):
    return sorted(meal_list, key=lambda x: MEAL_ORDER_MAP.get(x.get("meal_type", "不明"), 4))

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

def get_gemini_client():
    """Google GenAI SDK クライアントの初期化"""
    try:
        api_key = st.secrets.get("GEMINI_API_KEY", None)
        if api_key:
            return genai.Client(api_key=api_key)
        return genai.Client()
    except Exception as e:
        st.error(f"⚠️ Gemini API初期化エラー: GEMINI_API_KEY を確認してください。({e})")
        return None

ai_client = get_gemini_client()

# ---------------------------------------------------------
# 3. データ操作ヘルパー関数 (Firestore)
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
    """指定した日付範囲の食事データを一括取得"""
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

def fetch_daily_exercises(selected_date_str):
    if not db:
        return []
    try:
        docs = db.collection("exercises").where("date", "==", selected_date_str).get()
        return [d.to_dict() for d in docs]
    except Exception as e:
        st.error(f"運動データの取得エラー: {e}")
        return []

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

# ---------------------------------------------------------
# 4. AI解析ロジック (Gemini 3.6 Flash)
# ---------------------------------------------------------
def generate_journal_feedback(note):
    if not ai_client or not note.strip():
        return ""
    prompt = f"""
あなたは親切で温かいパーソナルボディメイク＆メンタルコーチです。
ユーザーの本日のジャーナル（振り返り・メモ）に対して、150文字程度でポジティブなフィードバックやアドバイスを提供してください。

ユーザーの振り返り:
{note}
"""
    try:
        response = ai_client.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt
        )
        return response.text
    except Exception as e:
        return f"フィードバックの生成に失敗しました: {e}"

def parse_and_save_meal(user_text, target_date_str, is_eating_out=False, restaurant_name="", dining_partners="", eating_out_comment=""):
    if not ai_client:
        return "AIクライアントが初期化されていません。GEMINI_API_KEYを確認してください。"

    rules = fetch_user_rules()
    rules_text = ""
    if rules:
        rules_text = "\n【ユーザー指定の辞書登録・優先計算ルール】\n" + "\n".join([f"- {r.get('title')}: {r.get('detail')}" for r in rules]) + "\n※上記の辞書登録にある単語が含まれている場合は、その定義（例: 黄身なし、専用レシピの栄養素等）を最優先してカロリー・PFCを計算してください。\n"

    prompt = f"""
あなたは優しく優秀なパーソナルボディメイクコーチです。
ユーザーの発言から「食事」に関するデータを抽出し、以下のJSON形式厳守で出力してください。
{rules_text}
対象日付: {target_date_str}

【抽出フォーマット】
{{
  "meals": [
    {{
      "meal_type": "朝食", // 発言内容や入力時間帯から「朝食」「昼食」「夕食」「間食」のいずれかを推測。特定できない場合は「不明」としてください
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

if not db:
    st.warning("⚠️ 現在データベース(Firestore)に接続できていません。Streamlit Community Cloudの Secrets 設定を確認してください。")

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
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📝 本日のデータ入力", 
    "📊 日次サマリー＆KPI", 
    "📈 習慣＆体組成の分析", 
    "📊 過去1週間の推移",
    "⚙️ 設定"
])

# ---------------------------------------------------------
# TAB 1: 本日のデータ入力 (メイン入力画面)
# ---------------------------------------------------------
with tab1:
    st.subheader("📅 記録対象日の選択")
    selected_date = st.date_input("入力・編集する日付 (年月日・曜日)", date.today(), key="main_date_input")
    selected_date_str = selected_date.strftime("%Y-%m-%d")
    st.markdown(f"**選択中の日付**: `{format_date_with_weekday(selected_date)}`")

    # 既存データの取得
    exist_meals = sort_meals(fetch_daily_meals(selected_date_str))
    exist_exercises = fetch_daily_exercises(selected_date_str)
    exist_habit = fetch_daily_habit(selected_date_str)
    exist_journal = fetch_journal(selected_date_str)
    exist_body = fetch_body_comp(selected_date_str)

    st.divider()

    # 1. 習慣化チェックイン
    st.subheader("🏋️ 1. 習慣化チェックイン")
    habit_options = ["目標達成", "一応やった", "未実施", "未記録"]

    def get_habit_idx(val):
        return habit_options.index(val) if val in habit_options else 3

    # コールバック関数: フォーム送信時に安全にDB保存と状態更新を実行
    def save_habit_callback(date_str):
        gym_v = st.session_state.get("h_radio_gym", "未記録")
        eng_v = st.session_state.get("h_radio_eng", "未記録")
        rest_v = st.session_state.get("h_radio_rest", "未記録")
        memo_v = st.session_state.get("h_memo_field", "")
        save_daily_habit(date_str, gym_v, eng_v, rest_v, memo_v)
        st.session_state["habit_saved_msg"] = True

    if "habit_saved_msg" in st.session_state and st.session_state["habit_saved_msg"]:
        st.success("習慣化データを保存しました。")
        st.session_state["habit_saved_msg"] = False

    with st.form("habit_input_form"):
        st.write("各習慣の達成状況を選択してください（1クリックで入力可能）:")
        h_col1, h_col2, h_col3 = st.columns(3)
        with h_col1:
            gym_val = st.radio("🏃 運動", habit_options, index=get_habit_idx(exist_habit.get("gym", "未記録")), horizontal=True, key="h_radio_gym")
        with h_col2:
            eng_val = st.radio("📚 英語学習", habit_options, index=get_habit_idx(exist_habit.get("english", "未記録")), horizontal=True, key="h_radio_eng")
        with h_col3:
            rest_val = st.radio("🍺 休肝日", habit_options, index=get_habit_idx(exist_habit.get("rest_day", "未記録")), horizontal=True, key="h_radio_rest")
            
        h_memo = st.text_input("習慣メモ", value=exist_habit.get("memo", ""), placeholder="例: 脚トレ実施 / 瞬間英作文20分", key="h_memo_field")
        
        st.form_submit_button("習慣化データを保存", on_click=save_habit_callback, args=(selected_date_str,))

    st.divider()

    # 2. 食事ログ入力
    st.subheader("🥗 2. 食事ログの入力")
    
    with st.expander("📖 単語辞書（カスタム栄養定義）の確認・追加"):
        user_rules = fetch_user_rules()
        if user_rules:
            st.markdown("**登録済みの辞書ルール:**")
            for r in user_rules:
                r_col1, r_col2 = st.columns([5, 1])
                r_col1.write(f"・**{r.get('title')}**: {r.get('detail')}")
                if r_col2.button("削除", key=f"del_rule_tab1_{r.get('doc_id')}"):
                    delete_user_rule(r.get('doc_id'))
                    st.rerun()
        else:
            st.caption("登録された単語辞書はありません。")
            
        with st.form("add_rule_form_tab1", clear_on_submit=True):
            r_title = st.text_input("単語・料理名", placeholder="例: ゆで卵")
            r_detail = st.text_area("計算ルール・仕様", placeholder="例: 黄身は食べないので白身のみのカロリー・タンパク質で計算する。")
            if st.form_submit_button("単語を辞書登録"):
                if r_title and r_detail:
                    save_user_rule(r_title, r_detail)
                    st.success(f"単語「{r_title}」を辞書に登録しました！")
                    st.rerun()

    st.markdown("**🤖 新規食事の入力（AI解析）**")
    if "meal_text_val" not in st.session_state:
        st.session_state["meal_text_val"] = ""

    meal_text = st.text_area("食事内容（時間帯の指定がない場合は現在の時間からAIが推測します）", value=st.session_state["meal_text_val"], placeholder="例: 昼食に丸の内のうなぎ屋で特上うな重を食べた。", key="meal_text_area")
    
    is_out = st.checkbox("🍔 外食・会食として記録する", key="chk_is_out")
    
    rest_name, partners, out_comment = "", "", ""
    if is_out:
        st.markdown("##### 🍺 外食詳細情報")
        m_col1, m_col2 = st.columns(2)
        rest_name = m_col1.text_input("店名・場所", key="input_rest_name")
        partners = m_col2.text_input("誰と（同行者）", key="input_partners")
        out_comment = st.text_input("外食に関するメモ・評価", key="input_out_comment")

    if st.button("AIで解析して食事を保存", type="primary", key="btn_save_meal"):
        if meal_text.strip():
            with st.spinner("AIが栄養素を解析中..."):
                adv = parse_and_save_meal(meal_text, selected_date_str, is_out, rest_name, partners, out_comment)
                st.session_state["meal_text_val"] = ""
                st.session_state["input_rest_name"] = ""
                st.session_state["input_partners"] = ""
                st.session_state["input_out_comment"] = ""
                st.success(f"保存完了: {adv}")
                st.rerun()
        else:
            st.warning("食事内容を入力してください。")

    if exist_meals:
        with st.expander(f"📋 登録済みの食事 ({len(exist_meals)} 件) ※朝食・昼食・夕食順", expanded=True):
            for idx, m in enumerate(exist_meals, 1):
                out_info = f" 【外食: {m.get('restaurant_name', '')}】" if m.get("is_eating_out") else ""
                meal_type = m.get("meal_type", "不明")
                st.write(f"**{idx}. [{meal_type}] {m.get('food_name')}** - {m.get('calories', 0)}kcal (P:{m.get('protein', 0)}g F:{m.get('fat', 0)}g C:{m.get('carbs', 0)}g){out_info}")
            st.caption("※食事の編集・削除は「日次サマリー&KPI」タブにて行えます。")

    st.divider()

    # 3. 運動ログ入力
    st.subheader("🏃 3. 運動ログの入力")

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
    if "ex_text_val" not in st.session_state:
        st.session_state["ex_text_val"] = ""

    with st.form("exercise_ai_form"):
        ex_text = st.text_area("その他の運動内容", value=st.session_state["ex_text_val"], placeholder="例: ベンチプレス 30分")
        if st.form_submit_button("AIで解析して運動を保存"):
            if ex_text.strip():
                with st.spinner("AIが消費カロリーを解析中..."):
                    adv = parse_and_save_exercise(ex_text, selected_date_str)
                    st.session_state["ex_text_val"] = ""
                    st.success(f"保存完了: {adv}")
                    st.rerun()
            else:
                st.warning("運動内容を入力してください。")

    if exist_exercises:
        with st.expander(f"📋 登録済みの運動 ({len(exist_exercises)} 件)", expanded=True):
            for idx, e in enumerate(exist_exercises, 1):
                st.write(f"{idx}. **{e.get('exercise_name')}** - {e.get('duration_min')}分 ({e.get('burned_calories')} kcal消費)")

    st.divider()

    # 4. ジャーナリング入力
    st.subheader("📖 4. 本日のジャーナリング（振り返り）")
    if "j_note_val" not in st.session_state:
        st.session_state["j_note_val"] = exist_journal.get("note", "") if exist_journal else ""

    with st.form("journal_input_form"):
        j_note = st.text_area(
            "振り返り・体調・気づき", 
            value=st.session_state["j_note_val"],
            height=100
        )
        if st.form_submit_button("ジャーナルを保存"):
            if j_note.strip():
                with st.spinner("Geminiがフィードバックを生成中..."):
                    fb = generate_journal_feedback(j_note)
                    save_journal(selected_date_str, j_note, fb)
                    st.session_state["j_note_val"] = ""
                    st.success("ジャーナルとAIフィードバックを保存しました！")
                    st.rerun()
            else:
                save_journal(selected_date_str, "", "")
                st.success("ジャーナルをクリアしました。")
                st.rerun()

    if exist_journal and exist_journal.get("note"):
        st.markdown(f"**📝 登録済みの振り返り ({format_date_with_weekday(selected_date_str)})**: {exist_journal.get('note')}")
        if exist_journal.get("ai_feedback"):
            st.info(f"🤖 **AIコーチからのフィードバック**:\n\n{exist_journal.get('ai_feedback')}")

    st.divider()

    # 5. 体組成データのCSVインポート
    st.subheader("⚙️ 5. 体組成データの入力 (CSV一括アップロード)")
    st.info("※対応形式: オムロン / タニタ等の体組成計CSVデータ（測定日、体重(kg)、体脂肪(%)、骨格筋量(kg)、基礎代謝(kcal) が含まれるデータ）")
    
    uploaded_file = st.file_uploader("体組成計のCSVデータをアップロード", type=["csv"])
    if uploaded_file is not None:
        if st.button("CSVデータをインポート"):
            try:
                df = pd.read_csv(uploaded_file)
                date_col = [c for c in df.columns if "測定" in c or "日付" in c or "date" in c.lower()]
                weight_col = [c for c in df.columns if "体重" in c or "weight" in c.lower()]
                fat_col = [c for c in df.columns if "体脂肪" in c or "fat" in c.lower()]
                muscle_col = [c for c in df.columns if "骨格筋" in c or "筋肉" in c or "muscle" in c.lower()]
                bmr_col = [c for c in df.columns if "基礎代謝" in c or "bmr" in c.lower()]

                if date_col and weight_col:
                    d_c = date_col[0]
                    w_c = weight_col[0]
                    f_c = fat_col[0] if fat_col else None
                    m_c = muscle_col[0] if muscle_col else None
                    b_c = bmr_col[0] if bmr_col else None

                    df['date_str'] = pd.to_datetime(df[d_c]).dt.strftime('%Y-%m-%d')
                    df['datetime'] = pd.to_datetime(df[d_c])
                    
                    df = df.sort_values('datetime')
                    df_daily = df.drop_duplicates(subset=['date_str'], keep='last')
                    
                    if db:
                        batch = db.batch()
                        count = 0
                        for _, row in df_daily.iterrows():
                            doc_ref = db.collection("body_composition").document(row['date_str'])
                            batch.set(doc_ref, {
                                "date": row['date_str'],
                                "weight": float(row[w_c]),
                                "body_fat": float(row[f_c]) if f_c and pd.notnull(row[f_c]) else 0.0,
                                "muscle_mass": float(row[m_c]) if m_c and pd.notnull(row[m_c]) else 0.0,
                                "bmr": float(row[b_c]) if b_c and pd.notnull(row[b_c]) else 0.0,
                                "updated_at": firestore.SERVER_TIMESTAMP
                            }, merge=True)
                            count += 1
                        batch.commit()
                        st.success(f"{count}日分の体組成データをFirestoreに一括登録しました！「習慣＆体組成の分析」タブにて反映をご確認いただけます。")
                else:
                    st.error("CSVの形式が異なります。対応するカラム（測定日、体重(kg) 等）が含まれるデータをアップロードしてください。")
            except Exception as e:
                st.error(f"インポート処理中にエラーが発生しました: {e}")

# ---------------------------------------------------------
# TAB 2: 日次サマリー ＆ KPI (日付選択機能付き)
# ---------------------------------------------------------
with tab2:
    st.subheader("📊 日次サマリー ＆ 該当日の明細")
    
    # 選択日付切り替え機能
    tab2_selected_date = st.date_input("表示する日付を選択", selected_date, key="summary_date_picker")
    tab2_selected_date_str = tab2_selected_date.strftime("%Y-%m-%d")
    
    st.markdown(f"#### 対象日: `{format_date_with_weekday(tab2_selected_date)}`")
    
    meals_summary = sort_meals(fetch_daily_meals(tab2_selected_date_str))
    exercises_summary = fetch_daily_exercises(tab2_selected_date_str)
    goals = fetch_user_goals()
    habit_summary = fetch_daily_habit(tab2_selected_date_str)
    
    tot_cal = sum(m.get("calories", 0) for m in meals_summary)
    tot_p = sum(m.get("protein", 0) for m in meals_summary)
    tot_f = sum(m.get("fat", 0) for m in meals_summary)
    tot_c = sum(m.get("carbs", 0) for m in meals_summary)
    tot_burn = sum(e.get("burned_calories", 0) for e in exercises_summary)
    
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("カロリー", f"{int(tot_cal)} kcal", f"{int(tot_cal - goals['target_cal'])} kcal")
    col2.metric("P (タンパク質)", f"{tot_p:.1f} g", f"{tot_p - goals['target_p']:.1f} g")
    col3.metric("F (脂質)", f"{tot_f:.1f} g", f"{tot_f - goals['target_f']:.1f} g")
    col4.metric("C (炭水化物)", f"{tot_c:.1f} g", f"{tot_c - goals['target_c']:.1f} g")
    col5.metric("運動消費", f"{int(tot_burn)} kcal", f"{len(exercises_summary)} 件")

    st.divider()

    st.markdown("##### 🏋️ 選択日の習慣達成ステータス")
    hc1, hc2, hc3 = st.columns(3)
    hc1.info(f"**運動**: {habit_summary.get('gym', '未記録')}")
    hc2.info(f"**英語学習**: {habit_summary.get('english', '未記録')}")
    hc3.info(f"**休肝日**: {habit_summary.get('rest_day', '未記録')}")

    st.divider()

    st.markdown("##### 🥗 食事明細＆外食記録（朝食・昼食・夕食順）")
    if meals_summary:
        for idx, m in enumerate(meals_summary, 1):
            m_type = m.get("meal_type", "不明")
            
            with st.container():
                col_info, col_edit, col_del = st.columns([6, 1.5, 1])
                with col_info:
                    if m.get("is_eating_out"):
                        st.warning(f"🍺 **{idx}. 【外食 / {m_type}】{m.get('food_name')}** ({m.get('calories')} kcal)\n"
                                   f"- 店名: {m.get('restaurant_name', '未入力')} / 同行者: {m.get('dining_partners', '未入力')}\n"
                                   f"- メモ: {m.get('eating_out_comment', 'なし')}")
                    else:
                        st.write(f"🍽️ **{idx}. [{m_type}] {m.get('food_name')}** - {m.get('calories')} kcal (P:{m.get('protein')}g, F:{m.get('fat')}g, C:{m.get('carbs')}g)")
                
                with col_del:
                    if st.button("🗑️ 削除", key=f"del_meal_tab2_{m.get('doc_id')}"):
                        if delete_meal(m.get("doc_id")):
                            st.success("削除しました！")
                            st.rerun()

                with col_edit:
                    with st.popover("✏️ 編集"):
                        st.markdown(f"**食事アイテムの編集**")
                        edit_food = st.text_input("品目名", value=m.get("food_name", ""), key=f"ef_name_{m.get('doc_id')}")
                        edit_type = st.selectbox("食事タイプ", ["朝食", "昼食", "夕食", "間食", "不明"], 
                                                 index=["朝食", "昼食", "夕食", "間食", "不明"].index(m.get("meal_type", "不明")) if m.get("meal_type") in ["朝食", "昼食", "夕食", "間食", "不明"] else 4, 
                                                 key=f"ef_type_{m.get('doc_id')}")
                        
                        ec1, ec2 = st.columns(2)
                        edit_cal = ec1.number_input("カロリー (kcal)", value=float(m.get("calories", 0)), key=f"ef_cal_{m.get('doc_id')}")
                        edit_p = ec2.number_input("タンパク質 P (g)", value=float(m.get("protein", 0)), key=f"ef_p_{m.get('doc_id')}")
                        edit_f = ec1.number_input("脂質 F (g)", value=float(m.get("fat", 0)), key=f"ef_f_{m.get('doc_id')}")
                        edit_c = ec2.number_input("炭水化物 C (g)", value=float(m.get("carbs", 0)), key=f"ef_c_{m.get('doc_id')}")
                        
                        edit_is_out = st.checkbox("🍔 外食・会食", value=bool(m.get("is_eating_out")), key=f"ef_isout_{m.get('doc_id')}")
                        edit_rest, edit_part, edit_comment = m.get("restaurant_name", ""), m.get("dining_partners", ""), m.get("eating_out_comment", "")
                        if edit_is_out:
                            edit_rest = st.text_input("店名・場所", value=m.get("restaurant_name", ""), key=f"ef_rest_{m.get('doc_id')}")
                            edit_part = st.text_input("同行者", value=m.get("dining_partners", ""), key=f"ef_part_{m.get('doc_id')}")
                            edit_comment = st.text_input("外食メモ", value=m.get("eating_out_comment", ""), key=f"ef_comm_{m.get('doc_id')}")

                        if st.button("更新を保存", key=f"save_edit_{m.get('doc_id')}"):
                            updated_data = {
                                "food_name": edit_food,
                                "meal_type": edit_type,
                                "calories": float(edit_cal),
                                "protein": float(edit_p),
                                "fat": float(edit_f),
                                "carbs": float(edit_c),
                                "is_eating_out": edit_is_out,
                                "restaurant_name": edit_rest if edit_is_out else "",
                                "dining_partners": edit_part if edit_is_out else "",
                                "eating_out_comment": edit_comment if edit_is_out else ""
                            }
                            if update_meal(m.get("doc_id"), updated_data):
                                st.success("更新しました！")
                                st.rerun()
                st.divider()
    else:
        st.caption("選択された日付の食事データはありません。")

# ---------------------------------------------------------
# TAB 3: 習慣 ＆ 体組成の分析
# ---------------------------------------------------------
with tab3:
    st.subheader("📈 習慣 ＆ 体組成データの分析")
    
    # --- 1. 習慣達成マトリクス ---
    st.markdown("### 🗓️ 過去30日間の習慣達成マトリクス（色分け一覧）")
    
    end_date = date.today()
    start_30d = end_date - timedelta(days=29)
    habits_30d = fetch_habits_range(start_30d.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
    
    date_list = [(start_30d + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(30)]
    habit_dict = {h.get("date"): h for h in habits_30d}
    
    items = ["運動", "英語学習", "休肝日"]
    item_keys = {"運動": "gym", "英語学習": "english", "休肝日": "rest_day"}
    
    score_map = {"未記録": 0, "未実施": 1, "一応やった": 2, "目標達成": 3}
    
    matrix_data = []
    text_matrix = []
    
    for item in items:
        row_scores = []
        row_texts = []
        k = item_keys[item]
        for d_str in date_list:
            h_record = habit_dict.get(d_str, {})
            st_val = h_record.get(k, "未記録")
            row_scores.append(score_map.get(st_val, 0))
            row_texts.append(f"{d_str}<br>{item}: {st_val}")
        matrix_data.append(row_scores)
        text_matrix.append(row_texts)
        
    colorscale = [
        [0.0, "#f3f4f6"],  # 未記録
        [0.33, "#93c5fd"], # 未実施
        [0.66, "#3b82f6"], # 一応やった
        [1.0, "#1d4ed8"]   # 目標達成
    ]
    
    fig_heatmap = px.imshow(
        matrix_data,
        x=date_list,
        y=items,
        color_continuous_scale=colorscale,
        range_color=[0, 3],
        aspect="auto",
        title="過去30日間の習慣達成結果"
    )
    fig_heatmap.update_traces(
        xgap=4,
        ygap=4,
        hovertemplate="%{customdata}<extra></extra>",
        customdata=text_matrix
    )
    fig_heatmap.update_coloraxes(showscale=False)
    fig_heatmap.update_xaxes(side="bottom", tickangle=-45)
    fig_heatmap.update_layout(
        margin=dict(l=60, r=20, t=50, b=60)
    )
    st.plotly_chart(fig_heatmap, use_container_width=True)

    st.divider()

    # --- 2. 体組成データの推移グラフ (体重非表示化) ---
    st.markdown("### ⚖️ 体組成データの推移 (体脂肪率・体脂肪量・骨格筋量)")
    all_body_data = fetch_all_body_comp()
    
    if all_body_data:
        df_body = pd.DataFrame(all_body_data)
        df_body['date_dt'] = pd.to_datetime(df_body['date'])
        df_body = df_body.sort_values('date_dt')
        
        if 'weight' in df_body.columns and 'body_fat' in df_body.columns:
            df_body['fat_mass'] = df_body['weight'] * (df_body['body_fat'] / 100.0)
            
        fig_body = px.line(
            df_body,
            x='date',
            y=['body_fat', 'fat_mass', 'muscle_mass'],
            labels={
                'date': '日付',
                'value': '測定値',
                'variable': '指標'
            },
            title="体組成データの経時変化 (※体重非表示)",
            markers=True
        )
        
        new_names = {
            'body_fat': '体脂肪率 (%)',
            'fat_mass': '体脂肪量 (kg)',
            'muscle_mass': '骨格筋量 (kg)'
        }
        fig_body.for_each_trace(lambda t: t.update(name = new_names.get(t.name, t.name)))
        
        st.plotly_chart(fig_body, use_container_width=True)
    else:
        st.info("体組成データがまだ登録されていません。「本日のデータ入力」タブからCSVをアップロードしてください。")

# ---------------------------------------------------------
# TAB 4: 過去1週間の推移
# ---------------------------------------------------------
with tab4:
    st.subheader("📊 過去1週間の栄養摂取推移 (カロリー ＆ PFC)")
    
    today = date.today()
    start_7d = today - timedelta(days=6)
    
    dates_7d = [(start_7d + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
    meals_7d = fetch_meals_range(start_7d.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))
    
    daily_summary = []
    goals = fetch_user_goals()
    
    for d_str in dates_7d:
        day_meals = [m for m in meals_7d if m.get("date") == d_str]
        c_sum = sum(m.get("calories", 0) for m in day_meals)
        p_sum = sum(m.get("protein", 0) for m in day_meals)
        f_sum = sum(m.get("fat", 0) for m in day_meals)
        cb_sum = sum(m.get("carbs", 0) for m in day_meals)
        
        daily_summary.append({
            "date": d_str,
            "calories": c_sum,
            "protein": p_sum,
            "fat": f_sum,
            "carbs": cb_sum
        })
        
    df_7d = pd.DataFrame(daily_summary)
    
    fig_cal = px.bar(
        df_7d,
        x="date",
        y="calories",
        text_auto=".0f",
        title="過去7日間の合計摂取カロリー推移",
        labels={"date": "日付", "calories": "摂取カロリー (kcal)"}
    )
    fig_cal.add_hline(
        y=goals.get("target_cal", 2200),
        line_dash="dash",
        line_color="red",
        annotation_text=f"目標カロリー ({int(goals.get('target_cal', 2200))} kcal)",
        annotation_position="top right"
    )
    st.plotly_chart(fig_cal, use_container_width=True)
    
    st.divider()
    
    st.markdown("### 🥗 PFC別 摂取量推移")
    
    fig_p = px.bar(
        df_7d,
        x="date",
        y="protein",
        text_auto=".1f",
        title="過去7日間の P (タンパク質) 摂取量推移 (g)",
        labels={"date": "日付", "protein": "タンパク質 (g)"},
        color_discrete_sequence=["#3b82f6"]
    )
    fig_p.add_hline(
        y=goals.get("target_p", 160),
        line_dash="dash",
        line_color="red",
        annotation_text=f"目標 P ({int(goals.get('target_p', 160))} g)",
        annotation_position="top right"
    )
    st.plotly_chart(fig_p, use_container_width=True)
    
    fig_f = px.bar(
        df_7d,
        x="date",
        y="fat",
        text_auto=".1f",
        title="過去7日間の F (脂質) 摂取量推移 (g)",
        labels={"date": "日付", "fat": "脂質 (g)"},
        color_discrete_sequence=["#f59e0b"]
    )
    fig_f.add_hline(
        y=goals.get("target_f", 50),
        line_dash="dash",
        line_color="red",
        annotation_text=f"目標 F ({int(goals.get('target_f', 50))} g)",
        annotation_position="top right"
    )
    st.plotly_chart(fig_f, use_container_width=True)
    
    fig_c = px.bar(
        df_7d,
        x="date",
        y="carbs",
        text_auto=".1f",
        title="過去7日間の C (炭水化物) 摂取量推移 (g)",
        labels={"date": "日付", "carbs": "炭水化物 (g)"},
        color_discrete_sequence=["#10b981"]
    )
    fig_c.add_hline(
        y=goals.get("target_c", 250),
        line_dash="dash",
        line_color="red",
        annotation_text=f"目標 C ({int(goals.get('target_c', 250))} g)",
        annotation_position="top right"
    )
    st.plotly_chart(fig_c, use_container_width=True)

# ---------------------------------------------------------
# TAB 5: 設定
# ---------------------------------------------------------
with tab5:
    st.subheader("⚙️ アプリ・目標設定")
    st.write("サイドバーから目標マクロ（カロリー、PFC）を変更・保存できます。")
