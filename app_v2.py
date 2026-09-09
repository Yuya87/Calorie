import streamlit as st
import datetime
import pandas as pd
import plotly.express as px
from google.cloud import firestore
from google.oauth2 import service_account
from google import genai
from google.genai import types
import json

# ==========================================
# 0. ページ設定 & デザインカスタマイズ
# ==========================================
st.set_page_config(
    page_title="Body Make AI Tracker",
    page_icon="💪",
    layout="wide"
)

# モバイル・ダークモード最適化CSS
st.markdown("""
<style>
    .main .block-container {
        padding-top: 1.5rem;
        padding-bottom: 3rem;
    }
    .stMetric {
        background-color: #1e222a;
        padding: 10px;
        border-radius: 8px;
        border: 1px solid #313a46;
    }
    div[data-testid="stExpander"] {
        border: 1px solid #313a46;
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)

# Secrets 存在チェック（[gcp_service_account] または textkey の両方に対応）
has_firestore_key = "textkey" in st.secrets or "gcp_service_account" in st.secrets
has_gemini_key = "GEMINI_API_KEY" in st.secrets

if not has_firestore_key or not has_gemini_key:
    st.error("⚠️ Streamlit Community Cloudの Secrets が設定されていないか、キーが不足しています。")
    st.info("""
    **【設定手順】**
    1. 画面右下の **Manage app** ＞ **Settings** ＞ **Secrets** を開きます。
    2. `GEMINI_API_KEY` と、Firestore用サービスアカウントキー（`[gcp_service_account]` または `textkey`）を設定してください。
    """)
    st.stop()

# ==========================================
# 1. タイムゾーン & 初期化処理
# ==========================================
VN_TZ = datetime.timezone(datetime.timedelta(hours=7))

def get_vn_now():
    return datetime.datetime.now(VN_TZ)

def get_vn_today():
    return get_vn_now().date()

# ==========================================
# 2. クラウドサービス接続（Firestore / Gemini）
# ==========================================
@st.cache_resource
def get_firestore_client():
    if "textkey" in st.secrets:
        key_dict = json.loads(st.secrets["textkey"])
    elif "gcp_service_account" in st.secrets:
        key_dict = dict(st.secrets["gcp_service_account"])
    else:
        raise KeyError("Firestore用の認証キーが見つかりません。")

    # TOMLパース時の \n 文字列エスケープ補正
    if "private_key" in key_dict and isinstance(key_dict["private_key"], str):
        key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")

    creds = service_account.Credentials.from_service_account_info(key_dict)
    return firestore.Client(credentials=creds, project=key_dict["project_id"])

db = get_firestore_client()

@st.cache_resource
def get_gemini_client():
    api_key = st.secrets["GEMINI_API_KEY"]
    return genai.Client(api_key=api_key)

ai_client = get_gemini_client()

# ==========================================
# 3. Firestore データ操作関数群
# ==========================================
def get_user_goals():
    docs = db.collection("user_goals").order_by("updated_at", direction=firestore.Query.DESCENDING).limit(1).get()
    if docs:
        data = docs[0].to_dict()
        return data.get("target_cal", 2200.0), data.get("target_p", 160.0), data.get("target_f", 50.0), data.get("target_c", 250.0)
    return 2200.0, 160.0, 50.0, 250.0

def save_user_goals(cal, p, f, c):
    db.collection("user_goals").add({
        "target_cal": float(cal),
        "target_p": float(p),
        "target_f": float(f),
        "target_c": float(c),
        "updated_at": firestore.SERVER_TIMESTAMP
    })

def get_user_rules():
    doc = db.collection("settings").document("user_rules").get()
    if doc.exists:
        return doc.to_dict().get("rules_text", "")
    return ""

def save_user_rules(rules_text):
    db.collection("settings").document("user_rules").set({"rules_text": rules_text})

def fetch_logs_by_date(date_str):
    meals_docs = db.collection("meals").where("date", "==", date_str).get()
    meals = [{"id": d.id, **d.to_dict()} for d in meals_docs]
    
    ex_docs = db.collection("exercises").where("date", "==", date_str).get()
    exercises = [{"id": d.id, **d.to_dict()} for d in ex_docs]
    
    body_doc = db.collection("body_composition").document(date_str).get()
    body = body_doc.to_dict() if body_doc.exists else None
    
    return meals, exercises, body

def delete_firestore_document(collection_name, doc_id):
    db.collection(collection_name).document(doc_id).delete()

# ==========================================
# 4. Gemini 連携・プロンプト定義
# ==========================================
def get_system_prompt():
    rules_text = get_user_rules()
    prompt = f"""
あなたはユーザー専属の「AIボディメイク・栄養アドバイザー」です。
ユーザーの発言（食事内容、運動内容、体重・体組成データ、または雑談・質問）を解析し、適切なレスポンスを出力してください。

【ユーザー定義のログ計算ルール】
ユーザーが定義した以下の特別ルール・マスターデータを優先して計算に適用してください。
{rules_text}

【重要指示】
1. ユーザーが食事、運動、体重・体組成を報告した場合、必ず以下の厳密なJSON構造を含むレスポンスを生成してください。
2. ユーザー報告内にデータ登録（食事・運動・体組成）が含まれる場合は、JSONオブジェクト内の "has_log_data" を true にし、該当フィールドに値を設定してください。
3. 日常会話や質問のみでログデータが含まれない場合は、"has_log_data" を false とし、データ用フィールドは null または空配列にしてください。
4. アルコール（お酒）が入力に含まれる場合は、アルコールの純エタノール重量(g)を推定量で計算し "alcohol_g" に入れてください。
5. カロリー・PFC・運動消費カロリーは客観的かつ現実的な推定量（float）で算出してください。
6. JSONブロックの前後または内部で、アドバイザーとしてのフレンドリーで実践的なコメント（アドバイス、労い、質問への回答）を "reply_text" に格納してください。

【出力JSONフォーマット仕様】
必ず以下のJSON構造を守って出力してください（Markdownの ```json ... ``` コードブロックで囲んでください）。

{{
  "reply_text": "ユーザーへのアドバイスや返答メッセージ（日本語）",
  "has_log_data": true または false,
  "meals": [
    {{
      "food_name": "食品名",
      "calories": 0.0,
      "protein": 0.0,
      "fat": 0.0,
      "carbs": 0.0,
      "alcohol_g": 0.0
    }}
  ],
  "exercises": [
    {{
      "exercise_name": "種目名",
      "duration_min": 0.0,
      "burned_calories": 0.0
    }}
  ],
  "body_composition": {{
    "weight": null または 数値,
    "body_fat": null または 数値,
    "muscle_mass": null または 数値,
    "bmr": null または 数値
  }}
}}
"""
    return prompt

def call_gemini_api(chat_history_messages, user_input, selected_date_str):
    system_instruction = get_system_prompt()
    
    context_prefix = f"【対象日付: {selected_date_str}】\n"
    full_user_input = context_prefix + user_input
    
    contents = []
    for msg in chat_history_messages:
        role = "user" if msg["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])]))
    
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=full_user_input)]))
    
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=0.2,
        response_mime_type="application/json"
    )
    
    response = ai_client.models.generate_content(
        model="gemini-3.6-flash",
        contents=contents,
        config=config
    )
    
    return response.text

def process_and_save_ai_response(response_raw_text, target_date_str):
    try:
        data = json.loads(response_raw_text)
    except Exception as e:
        return f"レスポンスの解析に失敗しました: {e}", False

    reply_text = data.get("reply_text", "ログを処理しました。")
    has_log = data.get("has_log_data", False)
    
    if not has_log:
        return reply_text, False

    saved_items = []
    
    # 食事ログ保存
    meals = data.get("meals", [])
    for m in meals:
        if m.get("food_name"):
            db.collection("meals").add({
                "date": target_date_str,
                "food_name": str(m.get("food_name")),
                "calories": float(m.get("calories", 0.0)),
                "protein": float(m.get("protein", 0.0)),
                "fat": float(m.get("fat", 0.0)),
                "carbs": float(m.get("carbs", 0.0)),
                "alcohol_g": float(m.get("alcohol_g", 0.0)),
                "created_at": firestore.SERVER_TIMESTAMP
            })
            saved_items.append(f"🍽️ {m.get('food_name')}")
            
    # 運動ログ保存
    exercises = data.get("exercises", [])
    for ex in exercises:
        if ex.get("exercise_name"):
            db.collection("exercises").add({
                "date": target_date_str,
                "exercise_name": str(ex.get("exercise_name")),
                "duration_min": float(ex.get("duration_min", 0.0)),
                "burned_calories": float(ex.get("burned_calories", 0.0)),
                "created_at": firestore.SERVER_TIMESTAMP
            })
            saved_items.append(f"🏃 {ex.get('exercise_name')}")
            
    # 体組成データ保存
    body = data.get("body_composition", {})
    if body and any(v is not None for v in body.values()):
        body_doc_ref = db.collection("body_composition").document(target_date_str)
        existing = body_doc_ref.get().to_dict() if body_doc_ref.get().exists else {}
        
        update_data = {"date": target_date_str}
        if body.get("weight") is not None: update_data["weight"] = float(body["weight"])
        if body.get("body_fat") is not None: update_data["body_fat"] = float(body["body_fat"])
        if body.get("muscle_mass") is not None: update_data["muscle_mass"] = float(body["muscle_mass"])
        if body.get("bmr") is not None: update_data["bmr"] = float(body["bmr"])
        
        existing.update(update_data)
        body_doc_ref.set(existing)
        saved_items.append(f"⚖️ 体組成データ ({target_date_str})")

    log_summary = ""
    if saved_items:
        log_summary = "\n\n**【登録されたデータ】**\n- " + "\n- ".join(saved_items)
        
    return reply_text + log_summary, True

# ==========================================
# 5. UI レンダリング・メイン処理
# ==========================================

# セッション状態の初期化
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

# ヘッダーエリア
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.title("💪 AI Body Make Tracker")
with col_h2:
    selected_date = st.date_input("記録対象日", value=get_vn_today())
    selected_date_str = selected_date.strftime("%Y-%m-%d")

# タブ構成
tab1, tab2, tab3, tab4 = st.tabs(["💬 AIログ解析チャット", "📊 日次サマリー", "📈 履歴＆グラフ分析", "⚙️ 設定"])

# ------------------------------------------
# TAB 1: AIログ解析チャット
# ------------------------------------------
with tab1:
    st.caption(f"📅 現在の記録対象日: **{selected_date_str}**（日付を変更する場合は右上のカレンダーで選択）")
    
    # チャット履歴表示
    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # ユーザー入力
    user_input = st.chat_input("例: 朝食にプロテイン20gとゆで卵白身2個、ベンチプレス40分。体重68.5kg 体脂肪15%")
    
    if user_input:
        # ユーザー発言表示
        st.session_state.chat_messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)
            
        # AI応答処理
        with st.chat_message("assistant"):
            with st.spinner("AIが解析・データ更新中..."):
                try:
                    raw_response = call_gemini_api(
                        st.session_state.chat_messages[:-1], 
                        user_input, 
                        selected_date_str
                    )
                    final_reply, has_saved = process_and_save_ai_response(raw_response, selected_date_str)
                    st.markdown(final_reply)
                    st.session_state.chat_messages.append({"role": "assistant", "content": final_reply})
                    if has_saved:
                        st.toast("データを保存しました！", icon="✅")
                except Exception as e:
                    err_msg = f"エラーが発生しました: {e}"
                    st.error(err_msg)

# ------------------------------------------
# TAB 2: 日次サマリー
# ------------------------------------------
with tab2:
    st.subheader(f"📊 {selected_date_str} の摂取・消費データ")
    
    meals, exercises, body = fetch_logs_by_date(selected_date_str)
    target_cal, target_p, target_f, target_c = get_user_goals()
    
    # 集計計算
    total_cal = sum(m.get("calories", 0.0) for m in meals)
    total_p = sum(m.get("protein", 0.0) for m in meals)
    total_f = sum(m.get("fat", 0.0) for m in meals)
    total_c = sum(m.get("carbs", 0.0) for m in meals)
    total_alc = sum(m.get("alcohol_g", 0.0) for m in meals)
    
    total_burned = sum(e.get("burned_calories", 0.0) for e in exercises) if exercises else 0.0
    
    # KPI表示
    kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
    kpi1.metric("カロリー", f"{total_cal:.0f} / {target_cal:.0f} kcal", f"{total_cal - target_cal:.0f} kcal")
    kpi2.metric("タンパク質 (P)", f"{total_p:.1f} / {target_p:.0f} g", f"{total_p - target_p:.1f} g")
    kpi3.metric("脂質 (F)", f"{total_f:.1f} / {target_f:.0f} g", f"{total_f - target_f:.1f} g")
    kpi4.metric("炭水化物 (C)", f"{total_c:.1f} / {target_c:.0f} g", f"{total_c - target_c:.1f} g")
    kpi5.metric("運動消費", f"{total_burned:.0f} kcal")
    
    if total_alc > 0:
        st.warning(f"🍷 アルコール摂取量: **{total_alc:.1f} g** (純エタノール換算)")

    st.divider()
    
    # 明細表示＆削除機能
    col_m, col_e = st.columns(2)
    
    with col_m:
        st.write("### 🍽️ 食事ログ一覧")
        if meals:
            for m in meals:
                c1, c2 = st.columns([4, 1])
                with c1:
                    st.write(f"**{m.get('food_name')}** | {m.get('calories',0):.0f} kcal (P:{m.get('protein',0):.1f}g F:{m.get('fat',0):.1f}g C:{m.get('carbs',0):.1f}g)")
                with c2:
                    if st.button("削除", key=f"del_m_{m['id']}"):
                        delete_firestore_document("meals", m['id'])
                        st.toast("削除しました")
                        st.rerun()
        else:
            st.info("食事ログがありません。")

    with col_e:
        st.write("### 🏃 運動ログ・体組成")
        if exercises:
            for e in exercises:
                c1, c2 = st.columns([4, 1])
                with c1:
                    st.write(f"**{e.get('exercise_name')}** | {e.get('duration_min',0):.0f}分 ({e.get('burned_calories',0):.0f} kcal消費)")
                with c2:
                    if st.button("削除", key=f"del_e_{e['id']}"):
                        delete_firestore_document("exercises", e['id'])
                        st.toast("削除しました")
                        st.rerun()
        else:
            st.info("運動ログがありません。")
            
        st.write("#### ⚖️ 体組成")
        if body:
            st.write(f"- 体重: **{body.get('weight', '-')}** kg")
            st.write(f"- 体脂肪率: **{body.get('body_fat', '-')}** %")
            st.write(f"- 筋肉量: **{body.get('muscle_mass', '-')}** kg")
        else:
            st.caption("体組成データ未登録")

# ------------------------------------------
# TAB 3: 履歴＆グラフ分析
# ------------------------------------------
with tab3:
    st.subheader("📈 トレンド分析")
    
    # 過去30日間の全データ取得
    all_meals = [d.to_dict() for d in db.collection("meals").get()]
    all_exercises = [d.to_dict() for d in db.collection("exercises").get()]
    all_body = [d.to_dict() for d in db.collection("body_composition").get()]
    
    # 体組成トレンドグラフ
    if all_body:
        df_body = pd.DataFrame(all_body).sort_values("date")
        st.write("### ⚖️ 体重・体脂肪率の推移")
        fig_body = px.line(df_body, x="date", y=["weight", "body_fat"], markers=True,
                           labels={"value": "数値", "variable": "項目", "date": "日付"},
                           title="体重(kg) / 体脂肪率(%) トレンド")
        st.plotly_chart(fig_body, use_container_width=True)
    else:
        st.info("体組成データが蓄積されるとグラフが表示されます。")
        
    # カロリー推移
    if all_meals:
        df_meals = pd.DataFrame(all_meals)
        df_cal = df_meals.groupby("date")["calories"].sum().reset_index().sort_values("date")
        st.write("### 🍎 日別摂取カロリー推移")
        fig_cal = px.bar(df_cal, x="date", y="calories", title="日別摂取カロリー (kcal)")
        st.plotly_chart(fig_cal, use_container_width=True)

# ------------------------------------------
# TAB 4: 設定
# ------------------------------------------
with tab4:
    st.subheader("⚙️ 目標設定 & カスタムルール")
    
    cur_cal, cur_p, cur_f, cur_c = get_user_goals()
    
    st.write("### 1. マクロ栄養素目標")
    with st.form("goals_form"):
        col1, col2 = st.columns(2)
        with col1:
            new_cal = st.number_input("目標カロリー (kcal)", value=float(cur_cal), step=50.0)
            new_p = st.number_input("目標 P (タンパク質g)", value=float(cur_p), step=5.0)
        with col2:
            new_f = st.number_input("目標 F (脂質g)", value=float(cur_f), step=5.0)
            new_c = st.number_input("目標 C (炭水化物g)", value=float(cur_c), step=5.0)
            
        submit_goals = st.form_submit_button("目標を更新")
        if submit_goals:
            save_user_goals(new_cal, new_p, new_f, new_c)
            st.success("目標設定を更新しました！")
            st.rerun()
            
    st.divider()
    
    st.write("### 2. ユーザー定義プロンプトルール")
    st.caption("よく食べる自作メニューや特定のプロテインの栄養成分ルールを入力しておくと、AIが優先して計算に使用します。")
    
    cur_rules = get_user_rules()
    with st.form("rules_form"):
        new_rules = st.text_area("カスタムルール（自由記述）", value=cur_rules, height=250)
        submit_rules = st.form_submit_button("ルールを保存")
        if submit_rules:
            save_user_rules(new_rules)
            st.success("カスタムルールを更新しました！次回以降のAI解析に適用されます。")
            st.rerun()
