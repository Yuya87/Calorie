import streamlit as st
import pandas as pd
import plotly.express as px
from PIL import Image
import io
import json
import datetime
from google.cloud import firestore
from google.oauth2 import service_account
from gemini_helper import analyze_meal_or_chat

# ------------------------------------------------------------------------------
# 1. Page Config & CSS
# ------------------------------------------------------------------------------
st.set_page_config(page_title="AIボディメイク", layout="wide")

st.markdown("""
    <style>
    h1 {
        font-size: 1.6rem !important;
        padding-top: 0.2rem !important;
        padding-bottom: 0.4rem !important;
    }
    h2 {
        font-size: 1.3rem !important;
    }
    h3 {
        font-size: 1.05rem !important;
    }
    </style>
""", unsafe_allow_html=True)

st.title("🏃 AIボディメイク")

# --- Firestore初期化 ---
@st.cache_resource
def get_db():
    sec = st.secrets["gcp_service_account"]
    key_dict = dict(sec)

    if "private_key" in key_dict:
        key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")

    creds = service_account.Credentials.from_service_account_info(key_dict)
    return firestore.Client(credentials=creds, project=key_dict["project_id"])
    
db = get_db()

def get_current_goals():
    default_goals = {"target_cal": 2000.0, "target_p": 120.0, "target_f": 50.0, "target_c": 200.0, "target_alc": 20.0}
    try:
        docs = db.collection("user_goals").order_by("updated_at", direction=firestore.Query.DESCENDING).limit(1).get()
        if docs:
            data = docs[0].to_dict()
            return {
                "target_cal": float(data.get("target_cal", default_goals["target_cal"])),
                "target_p": float(data.get("target_p", default_goals["target_p"])),
                "target_f": float(data.get("target_f", default_goals["target_f"])),
                "target_c": float(data.get("target_c", default_goals["target_c"])),
                "target_alc": float(data.get("target_alc", default_goals["target_alc"])),
            }
    except Exception:
        return default_goals
    return default_goals

def get_latest_bmr():
    try:
        docs = db.collection("body_composition").order_by("date", direction=firestore.Query.DESCENDING).limit(1).get()
        if docs:
            data = docs[0].to_dict()
            if data.get("bmr"):
                return float(data["bmr"])
            elif data.get("weight"):
                return round(float(data["weight"]) * 21.5, 0)
    except Exception:
        pass
    return 1500.0

def update_goals(cal, p, f, c, alc):
    db.collection("user_goals").add({
        "target_cal": cal, "target_p": p, "target_f": f, "target_c": c, "target_alc": alc,
        "updated_at": firestore.SERVER_TIMESTAMP
    })

# --- 前提条件（ユーザー定義ルール）管理関数 ---
def get_user_rules():
    try:
        docs = db.collection("user_rules").order_by("created_at", direction=firestore.Query.ASCENDING).get()
        rules = []
        for d in docs:
            data = d.to_dict()
            data["id"] = d.id
            rules.append(data)
        return rules
    except Exception:
        return []

def save_user_rule(rule_title, rule_detail):
    db.collection("user_rules").add({
        "title": rule_title,
        "detail": rule_detail,
        "created_at": firestore.SERVER_TIMESTAMP
    })

def delete_user_rule(doc_id):
    db.collection("user_rules").document(doc_id).delete()

def sanitize_firestore_data(data_dict):
    sanitized = {}
    for k, v in data_dict.items():
        if hasattr(v, "isoformat"):
            sanitized[k] = v.isoformat()
        elif hasattr(v, "__class__") and "DatetimeWithNanoseconds" in v.__class__.__name__:
            sanitized[k] = str(v)
        else:
            sanitized[k] = v
    return sanitized

def get_recent_logs_for_context():
    try:
        meals_docs = db.collection("meals").order_by("created_at", direction=firestore.Query.DESCENDING).limit(10).get()
    except Exception:
        meals_docs = []

    try:
        ex_docs = db.collection("exercises").order_by("created_at", direction=firestore.Query.DESCENDING).limit(10).get()
    except Exception:
        ex_docs = []

    logs = []
    for d in meals_docs:
        data = sanitize_firestore_data(d.to_dict())
        data["doc_id"] = d.id
        data["collection"] = "meals"
        logs.append(data)

    for d in ex_docs:
        data = sanitize_firestore_data(d.to_dict())
        data["doc_id"] = d.id
        data["collection"] = "exercises"
        logs.append(data)

    return logs

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "こんにちは！AIボディメイクアシスタントです。食事や運動ログの登録、日付変更、修正、削除など気軽にお申し付けください！"}
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
    new_alc = st.number_input("目標 純アルコール (g)", value=float(current_goals.get('target_alc', 20.0)), step=5.0)
    if st.form_submit_button("目標を更新"):
        update_goals(new_cal, new_p, new_f, new_c, new_alc)
        st.sidebar.success("目標を更新しました！")
        st.rerun()

st.sidebar.divider()
st.sidebar.metric("現在の適用基礎代謝 (BMR)", f"{latest_bmr:.0f} kcal", help="タニタの体組成データより自動適用中")

# タブ定義
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "💬 AI対話・記録", 
    "📊 栄養・アルコール管理", 
    "🔥 カロリー収支 & 運動", 
    "⚖️ 体組成 (タニタ)",
    "⚙️ ログルール設定"
])

# --- TAB 1: AI対話 ---
with tab1:
    st.header("AIアシスタントと会話して記録・修正")
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    uploaded_img = st.file_uploader("写真を送信", type=["jpg", "jpeg", "png"], key="meal_photo")
    image_obj = Image.open(uploaded_img) if uploaded_img else None

    user_input = st.chat_input("例: 昨日の夜のカレーの日付を今日に変更して / さっきの記録を削除して")

    if user_input or (uploaded_img and st.button("写真を送信")):
        input_text = user_input if user_input else "写真を送信しました。"
        st.session_state.messages.append({"role": "user", "content": input_text})
        with st.chat_message("user"):
            st.write(input_text)

        with st.chat_message("assistant"):
            with st.spinner("解析・記録中..."):
                recent_logs = get_recent_logs_for_context()
                user_rules = get_user_rules()
                
                rules_text = ""
                if user_rules:
                    rules_text = "\n【ユーザー定義の前提ルール・レシピ仕様】\n" + "\n".join([f"- {r['title']}: {r['detail']}" for r in user_rules])

                context_logs = list(recent_logs)
                if rules_text:
                    context_logs.append({"system_user_rules": rules_text})

                res = analyze_meal_or_chat(
                    st.session_state.messages,
                    user_text=input_text,
                    image=image_obj,
                    existing_logs=context_logs
                )

                response_text = res.get("assistant_response", "了解しました！")
                action_type = res.get("action_type", "GENERAL_CHAT")
                target_date = res.get("target_date") or pd.Timestamp.now().strftime('%Y-%m-%d')

                # 食事ログ追加
                if action_type == "MEAL_LOG" and res.get("meal_data"):
                    items = res["meal_data"].get("items", [res["meal_data"]])
                    saved_summary = []
                    for m in items:
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
                        alc_info = f" (Alc:{m.get('alcohol_g', 0)}g)" if m.get('alcohol_g', 0) > 0 else ""
                        saved_summary.append(f"• {m.get('food_name')} ({m.get('calories')}kcal / P:{m.get('protein')}g F:{m.get('fat')}g C:{m.get('carbs')}g){alc_info}")
                    
                    response_text += f"\n\n✅ **食事記録完了 [{target_date}]**:\n" + "\n".join(saved_summary)

                # 運動ログ追加
                elif action_type == "EXERCISE_LOG" and res.get("exercise_data"):
                    items = res["exercise_data"].get("items", [res["exercise_data"]])
                    saved_summary = []
                    for e in items:
                        db.collection("exercises").add({
                            "date": target_date,
                            "exercise_name": e.get('exercise_name', '運動'),
                            "duration_min": float(e.get('duration_min', 0)),
                            "burned_calories": float(e.get('burned_calories', 0)),
                            "created_at": firestore.SERVER_TIMESTAMP
                        })
                        saved_summary.append(f"• {e.get('exercise_name')} {e.get('duration_min')}分 ({e.get('burned_calories')}kcal消費)")
                    
                    response_text += f"\n\n🏋️ **運動記録完了 [{target_date}]**:\n" + "\n".join(saved_summary)

                # ログの更新（食事・運動共通の日付/内容更新）
                elif action_type == "UPDATE_LOG" and res.get("target_doc_id") and res.get("target_collection"):
                    coll = res["target_collection"]
                    doc_id = res["target_doc_id"]
                    doc_ref = db.collection(coll).document(doc_id)

                    update_fields = {}
                    if res.get("target_date"):
                        update_fields["date"] = res["target_date"]

                    if coll == "meals" and res.get("meal_data"):
                        m = res["meal_data"]
                        if "items" in m and len(m["items"]) > 0: m = m["items"][0]
                        for k in ['food_name', 'calories', 'protein', 'fat', 'carbs', 'alcohol_g']:
                            if k in m and m[k] is not None: update_fields[k] = m[k]
                    elif coll == "exercises" and res.get("exercise_data"):
                        e = res["exercise_data"]
                        if "items" in e and len(e["items"]) > 0: e = e["items"][0]
                        for k in ['exercise_name', 'duration_min', 'burned_calories']:
                            if k in e and e[k] is not None: update_fields[k] = e[k]

                    if update_fields:
                        doc_ref.update(update_fields)
                        date_info = f" (日付: {update_fields['date']})" if "date" in update_fields else ""
                        response_text += f"\n\n✏️ **ログ更新完了**{date_info}"

                # ログの削除
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
                                 g.get("target_c", current_goals['target_c']),
                                 g.get("target_alc", current_goals.get('target_alc', 20.0)))
                    response_text += f"\n\n🎯 **目標設定更新完了**"
                    st.rerun()

                st.write(response_text)
                st.session_state.messages.append({"role": "assistant", "content": response_text})

# --- TAB 2: 栄養＆アルコール管理 ---
with tab2:
    st.header("日別 PFC ＆ アルコール摂取管理")
    
    docs = db.collection("meals").get()
    meal_list = [d.to_dict() for d in docs]

    if meal_list:
        df_m = pd.DataFrame(meal_list)

        for col in ['calories', 'protein', 'fat', 'carbs', 'alcohol_g']:
            if col in df_m.columns:
                df_m[col] = pd.to_numeric(df_m[col], errors='coerce').fillna(0)
            else:
                df_m[col] = 0.0

        df_meals = df_m.groupby('date').agg({
            'calories': 'sum', 'protein': 'sum', 'fat': 'sum', 'carbs': 'sum', 'alcohol_g': 'sum'
        }).reset_index().sort_values('date')

        latest = df_meals.iloc[-1]
        st.subheader(f"🎯 本日 ({latest['date']}) の達成状況")
        
        c1, c2, c3, c4 = st.columns(4)
        
        with c1:
            cal_val = latest['calories']
            cal_diff = cal_val - current_goals['target_cal']
            st.metric("摂取カロリー", f"{cal_val:.0f} kcal", f"{cal_diff:+.0f} kcal")
            st.progress(min(1.0, max(0.0, cal_val / current_goals['target_cal'])), text=f"目標: {current_goals['target_cal']:.0f} kcal")

        with c2:
            p_val = latest['protein']
            p_diff = p_val - current_goals['target_p']
            st.metric("Protein (P)", f"{p_val:.1f} g", f"{p_diff:+.1f} g")
            st.progress(min(1.0, max(0.0, p_val / current_goals['target_p'])), text=f"目標: {current_goals['target_p']:.0f}g")

        with c3:
            f_val = latest['fat']
            f_diff = f_val - current_goals['target_f']
            st.metric("Fat (F)", f"{f_val:.1f} g", f"{f_diff:+.1f} g")
            st.progress(min(1.0, max(0.0, f_val / current_goals['target_f'])), text=f"目標: {current_goals['target_f']:.0f}g")

        with c4:
            c_val = latest['carbs']
            c_diff = c_val - current_goals['target_c']
            st.metric("Carbs (C)", f"{c_val:.1f} g", f"{c_diff:+.1f} g")
            st.progress(min(1.0, max(0.0, c_val / current_goals['target_c'])), text=f"目標: {current_goals['target_c']:.0f}g")

        st.markdown("---")

        # ----------------------------------------------------------------------
        # 【上段】直近3週間の月〜日 積み上げ比較グラフ
        # ----------------------------------------------------------------------
        st.subheader("🗓️ 直近3週間の摂取カロリー比較（月〜日 積み上げ）")
        
        df_meals['dt'] = pd.to_datetime(df_meals['date'])
        
        # 今日を基準に 今週(0), 先週(1), 2週前(2) の開始（月曜日）を算出
        today = datetime.date.today()
        current_monday = today - datetime.timedelta(days=today.weekday())
        
        week_defs = [
            {"label": "2週前", "start": current_monday - datetime.timedelta(weeks=2)},
            {"label": "先週", "start": current_monday - datetime.timedelta(weeks=1)},
            {"label": "今週", "start": current_monday}
        ]

        day_order_map = {0: '1.月', 1: '2.火', 2: '3.水', 3: '4.木', 4: '5.金', 5: '6.土', 6: '7.日'}

        stacked_rows = []
        for w in week_defs:
            w_start = w["start"]
            w_end = w_start + datetime.timedelta(days=6)
            
            # 当該期間のデータをフィルタリング
            mask = (df_meals['dt'].dt.date >= w_start) & (df_meals['dt'].dt.date <= w_end)
            df_w = df_meals[mask].copy()
            
            if not df_w.empty:
                df_w['week_label'] = w["label"]
                df_w['day_label'] = df_w['dt'].dt.weekday.map(day_order_map)
                for _, r in df_w.iterrows():
                    stacked_rows.append({
                        'week_label': w["label"],
                        'day_label': r['day_label'],
                        'calories': r['calories']
                    })

        if stacked_rows:
            df_3weeks = pd.DataFrame(stacked_rows)
            weekly_target_cal = current_goals['target_cal'] * 7.0

            fig_3w = px.bar(
                df_3weeks,
                x='week_label',
                y='calories',
                color='day_label',
                title="2週前 vs 先週 vs 今週（曜日別積み上げカロリー）",
                labels={'week_label': '週', 'calories': '摂取カロリー (kcal)', 'day_label': '曜日'},
                category_orders={
                    'week_label': ['2週前', '先週', '今週'],
                    'day_label': ['1.月', '2.火', '3.水', '4.木', '5.金', '6.土', '7.日']
                },
                color_discrete_sequence=px.colors.qualitative.Pastel
            )
            
            # 7日間の目標カロリーラインを追加
            fig_3w.add_hline(
                y=weekly_target_cal, 
                line_dash="dash", 
                line_color="red", 
                annotation_text=f"7日間目標: {weekly_target_cal:.0f} kcal", 
                annotation_position="top right"
            )
            fig_3w.update_layout(height=350, margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig_3w, use_container_width=True)
        else:
            st.info("過去3週間分の食事ログがありません。")

        st.markdown("---")

        # ----------------------------------------------------------------------
        # 【下段】日別推移の個別棒グラフ（カロリー, P, F, C, 純アルコール）
        # ----------------------------------------------------------------------
        st.subheader("📈 指標別 日推移グラフ")

        col_g1, col_g2 = st.columns(2)

        target_alc_val = current_goals.get('target_alc', 20.0)

        with col_g1:
            # 1. 摂取カロリー
            fig_cal = px.bar(df_meals, x='date', y='calories', title="摂取カロリー (kcal)", color_discrete_sequence=["#2A9D8F"])
            fig_cal.add_hline(y=current_goals['target_cal'], line_dash="dash", line_color="red", annotation_text="目標")
            fig_cal.update_layout(height=260, xaxis_title=None, margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig_cal, use_container_width=True)

            # 3. Fat (F)
            fig_f = px.bar(df_meals, x='date', y='fat', title="Fat / 脂質 (g)", color_discrete_sequence=["#FFAA00"])
            fig_f.add_hline(y=current_goals['target_f'], line_dash="dash", line_color="red", annotation_text="目標")
            fig_f.update_layout(height=260, xaxis_title=None, margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig_f, use_container_width=True)

            # 5. 純アルコール（目標ライン追加）
            fig_alc = px.bar(df_meals, x='date', y='alcohol_g', title="純アルコール (g)", color_discrete_sequence=["#9D4EDD"])
            fig_alc.add_hline(y=target_alc_val, line_dash="dash", line_color="red", annotation_text="目標上限")
            fig_alc.update_layout(height=260, xaxis_title=None, margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig_alc, use_container_width=True)

        with col_g2:
            # 2. Protein (P)
            fig_p = px.bar(df_meals, x='date', y='protein', title="Protein / タンパク質 (g)", color_discrete_sequence=["#FF4B4B"])
            fig_p.add_hline(y=current_goals['target_p'], line_dash="dash", line_color="red", annotation_text="目標")
            fig_p.update_layout(height=260, xaxis_title=None, margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig_p, use_container_width=True)

            # 4. Carbs (C)
            fig_c = px.bar(df_meals, x='date', y='carbs', title="Carbs / 炭水化物 (g)", color_discrete_sequence=["#00B4D8"])
            fig_c.add_hline(y=current_goals['target_c'], line_dash="dash", line_color="red", annotation_text="目標")
            fig_c.update_layout(height=260, xaxis_title=None, margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig_c, use_container_width=True)

        st.markdown("---")

        st.subheader("📋 直近3日間の活動サマリ")

        today = datetime.date.today()
        recent_3_dates = [(today - datetime.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(3)]

        ex_docs = db.collection("exercises").get()
        ex_list = [d.to_dict() for d in ex_docs]
        df_ex_all = pd.DataFrame(ex_list) if ex_list else pd.DataFrame()

        cols = st.columns(3)
        for idx, target_d in enumerate(recent_3_dates):
            with cols[idx]:
                day_label = "本日" if idx == 0 else ("昨日" if idx == 1 else "一昨日")
                st.markdown(f"**📅 {target_d} ({day_label})**")

                day_meals = df_m[df_m['date'] == target_d] if not df_m.empty else pd.DataFrame()
                with st.expander("🥗 食事内容", expanded=True):
                    if not day_meals.empty:
                        for _, row in day_meals.iterrows():
                            fname = row.get('food_name', '食事')
                            cal = row.get('calories', 0)
                            alc = row.get('alcohol_g', 0)
                            alc_str = f" / Alc:{alc:.0f}g" if alc > 0 else ""
                            st.markdown(f"- **{fname}** ({cal:.0f}kcal{alc_str})")
                    else:
                        st.caption("記録がありません")

                day_ex = df_ex_all[df_ex_all['date'] == target_d] if not df_ex_all.empty and 'date' in df_ex_all.columns else pd.DataFrame()
                with st.expander("🏃 運動内容", expanded=True):
                    if not day_ex.empty:
                        for _, row in day_ex.iterrows():
                            ename = row.get('exercise_name', '運動')
                            dur = row.get('duration_min', 0)
                            burn = row.get('burned_calories', 0)
                            st.markdown(f"- **{ename}** {dur:.0f}分 ({burn:.0f}kcal消費)")
                    else:
                        st.caption("記録がありません")

    else:
        st.info("データがまだありません。AI対話タブから食事を記録してください。")

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

# --- TAB 5: 前提条件・ログルール管理 ---
with tab5:
    st.header("⚙️ 食事・運動の前提ルール設定")
    st.caption("ここで登録したルールや自家製レシピの仕様は、AI対話時に自動的に考慮されます。")

    with st.expander("➕ 新しい前提ルール・レシピを追加する", expanded=True):
        with st.form("add_rule_form", clear_on_submit=True):
            rule_title = st.text_input("タイトル（例: 自家製無水カレー, ゆで卵）", placeholder="自家製無水カレー")
            rule_detail = st.text_area("ルールの詳細（例: ノンオイル、ささみ/胸肉使用、スパイス仕込み）", 
                                       placeholder="ノンオイルでささみ・胸肉を使用。スパイスから作成。1皿350kcal想定。")
            
            submit_rule = st.form_submit_button("ルールを保存")
            if submit_rule:
                if rule_title and rule_detail:
                    save_user_rule(rule_title, rule_detail)
                    st.success(f"ルール「{rule_title}」を保存しました！")
                    st.rerun()
                else:
                    st.warning("タイトルと詳細の両方を入力してください。")

    st.markdown("---")

    st.subheader("📋 登録済みのルール一覧")
    registered_rules = get_user_rules()

    if registered_rules:
        for r in registered_rules:
            r_id = r["id"]
            r_title = r.get("title", "無題")
            r_detail = r.get("detail", "")

            with st.container():
                col_info, col_btn = st.columns([5, 1])
                with col_info:
                    st.markdown(f"**📌 {r_title}**")
                    st.write(r_detail)
                with col_btn:
                    if st.button("削除", key=f"del_rule_{r_id}"):
                        delete_user_rule(r_id)
                        st.success("削除しました！")
                        st.rerun()
            st.divider()
    else:
        st.info("登録されているルールはありません。")
