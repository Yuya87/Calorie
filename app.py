import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
from PIL import Image
import os
import io
from gemini_helper import analyze_meal_or_chat

st.set_page_config(page_title="AIボディメイク＆体組成", layout="wide")
st.title("🏃 AIダイエット＆体組成・運動トラッカー")

def init_db():
    conn = sqlite3.connect('diet_app.db')
    c = conn.cursor()
    # 食事ログ
    c.execute('''
        CREATE TABLE IF NOT EXISTS meals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            food_name TEXT,
            calories REAL,
            protein REAL,
            fat REAL,
            carbs REAL,
            alcohol_g REAL DEFAULT 0
        )
    ''')
    # 運動ログ
    c.execute('''
        CREATE TABLE IF NOT EXISTS exercises (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            exercise_name TEXT,
            duration_min REAL,
            burned_calories REAL
        )
    ''')
    # 体組成ログ（基礎代謝 bmr を追加）
    c.execute('''
        CREATE TABLE IF NOT EXISTS body_composition (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE,
            weight REAL,
            body_fat REAL,
            muscle_mass REAL,
            bmr REAL
        )
    ''')
    # 目標設定
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_cal REAL,
            target_p REAL,
            target_f REAL,
            target_c REAL
        )
    ''')
    c.execute("SELECT COUNT(*) FROM user_goals")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO user_goals (target_cal, target_p, target_f, target_c) VALUES (2000, 120, 50, 200)")
    
    conn.commit()
    conn.close()

init_db()

def get_connection():
    return sqlite3.connect('diet_app.db')

def get_current_goals():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM user_goals ORDER BY id DESC LIMIT 1", conn)
    conn.close()
    if not df.empty:
        return df.iloc[0].to_dict()
    return {"target_cal": 2000, "target_p": 120, "target_f": 50, "target_c": 200}

def get_latest_bmr():
    """タニタの最新データから基礎代謝を取得。なければ標準推定値"""
    conn = get_connection()
    df = pd.read_sql_query("SELECT bmr, weight FROM body_composition WHERE bmr IS NOT NULL OR weight IS NOT NULL ORDER BY date DESC LIMIT 1", conn)
    conn.close()
    if not df.empty:
        if pd.notnull(df.iloc[0]['bmr']) and df.iloc[0]['bmr'] > 0:
            return float(df.iloc[0]['bmr'])
        elif pd.notnull(df.iloc[0]['weight']):
            # 体重からの簡易推測（ハリス・ベネディクト標準目安: 約21.5 kcal/kg）
            return round(float(df.iloc[0]['weight']) * 21.5, 0)
    return 1500.0  # デフォルト値

def update_goals(cal, p, f, c):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO user_goals (target_cal, target_p, target_f, target_c) VALUES (?, ?, ?, ?)", (cal, p, f, c))
    conn.commit()
    conn.close()

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "こんにちは！食事（写真・文章）、運動（ジム・ゴルフ等）なんでも記録してください。タニタの体組成データから自動取得した基礎代謝をもとに、カロリー収支を計算します！"}
    ]

# サイドバー設定
current_goals = get_current_goals()
latest_bmr = get_latest_bmr()

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
st.sidebar.metric("現在の適用基礎代謝 (BMR)", f"{latest_bmr:.0f} kcal", help="タニタの体組成データより自動参照中")

tab1, tab2, tab3, tab4 = st.tabs(["💬 AI対話・記録", "📊 栄養・アルコール管理", "🔥 カロリー収支 & 運動", "⚖️ 体組成 (タニタ)"])

# --- TAB 1: AI対話 ---
with tab1:
    st.header("AIアシスタントと会話して記録")
    
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    uploaded_img = st.file_uploader("写真を送信（食事・運動など任意）", type=["jpg", "jpeg", "png"], key="meal_photo")
    image_obj = Image.open(uploaded_img) if uploaded_img else None

    user_input = st.chat_input("例: ジムで傾斜をつけて30分歩いた / 夜にハイボール3杯と焼き鳥食べた")

    if user_input or (uploaded_img and st.button("写真を送信")):
        input_text = user_input if user_input else "写真を送信しました。"
        st.session_state.messages.append({"role": "user", "content": input_text})
        with st.chat_message("user"):
            st.write(input_text)

        with st.chat_message("assistant"):
            with st.spinner("思考・解析中..."):
                res = analyze_meal_or_chat(st.session_state.messages, user_text=input_text, image=image_obj)
                response_text = res.get("assistant_response", "了解しました！")
                action_type = res.get("action_type", "GENERAL_CHAT")
                
                # 食事・アルコール記録
                if action_type == "MEAL_LOG" and res.get("meal_data"):
                    m = res["meal_data"]
                    conn = get_connection()
                    c = conn.cursor()
                    c.execute('''
                        INSERT INTO meals (date, food_name, calories, protein, fat, carbs, alcohol_g)
                        VALUES (date('now'), ?, ?, ?, ?, ?, ?)
                    ''', (m.get('food_name', '食事'), m.get('calories', 0), m.get('protein', 0), m.get('fat', 0), m.get('carbs', 0), m.get('alcohol_g', 0)))
                    conn.commit()
                    conn.close()
                    alc_info = f" (純アルコール量: {m.get('alcohol_g', 0)}g)" if m.get('alcohol_g', 0) > 0 else ""
                    response_text += f"\n\n✅ **食事記録完了**: {m.get('food_name')} ({m.get('calories')}kcal / P:{m.get('protein')}g F:{m.get('fat')}g C:{m.get('carbs')}g){alc_info}"
                
                # 運動記録
                elif action_type == "EXERCISE_LOG" and res.get("exercise_data"):
                    e = res["exercise_data"]
                    conn = get_connection()
                    c = conn.cursor()
                    c.execute('''
                        INSERT INTO exercises (date, exercise_name, duration_min, burned_calories)
                        VALUES (date('now'), ?, ?, ?)
                    ''', (e.get('exercise_name', '運動'), e.get('duration_min', 0), e.get('burned_calories', 0)))
                    conn.commit()
                    conn.close()
                    response_text += f"\n\n🏋️ **運動記録完了**: {e.get('exercise_name')} {e.get('duration_min')}分 (推定消費カロリー: {e.get('burned_calories')}kcal)"

                # 目標更新
                elif action_type == "UPDATE_GOAL" and res.get("goal_data"):
                    g = res["goal_data"]
                    g_cal = g.get("target_cal") or current_goals['target_cal']
                    g_p = g.get("target_p") or current_goals['target_p']
                    g_f = g.get("target_f") or current_goals['target_f']
                    g_c = g.get("target_c") or current_goals['target_c']
                    update_goals(g_cal, g_p, g_f, g_c)
                    response_text += f"\n\n🎯 **目標設定更新完了**: {g_cal}kcal / P:{g_p}g F:{g_f}g C:{g_c}g"
                    st.rerun()

                st.write(response_text)
                st.session_state.messages.append({"role": "assistant", "content": response_text})

# --- TAB 2: 栄養＆アルコール管理 ---
with tab2:
    st.header("日別PFC ＆ アルコール摂取推移")
    conn = get_connection()
    df_meals = pd.read_sql_query("SELECT date, SUM(calories) as total_cal, SUM(protein) as total_p, SUM(fat) as total_f, SUM(carbs) as total_c, SUM(alcohol_g) as total_alc FROM meals GROUP BY date ORDER BY date", conn)
    conn.close()

    goals = get_current_goals()

    if not df_meals.empty:
        latest = df_meals.iloc[-1]
        st.subheader(f"📊 最新日 ({latest['date']}) の達成状況")
        
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("摂取カロリー", f"{latest['total_cal']:.0f} kcal", f"{latest['total_cal'] - goals['target_cal']:.0f} kcal")
        c2.metric("Protein (P)", f"{latest['total_p']:.1f} g", f"{latest['total_p'] - goals['target_p']:.1f} g")
        c3.metric("Fat (F)", f"{latest['total_f']:.1f} g", f"{latest['total_f'] - goals['target_f']:.1f} g")
        c4.metric("Carbs (C)", f"{latest['total_c']:.1f} g", f"{latest['total_c'] - goals['target_c']:.1f} g")
        c5.metric("純アルコール", f"{latest['total_alc']:.1f} g")

        st.subheader("📈 日別PFCバランス推移")
        fig_pfc = px.bar(df_meals, x='date', y=['total_p', 'total_f', 'total_c'], title="日別 PFC摂取量 (g)")
        st.plotly_chart(fig_pfc, use_container_width=True)

        st.subheader("🍺 摂取純アルコール量の推移 (g)")
        fig_alc = px.bar(df_meals, x='date', y='total_alc', title="アルコール摂取量 (g)", color_discrete_sequence=['#FFA500'])
        st.plotly_chart(fig_alc, use_container_width=True)
    else:
        st.info("食事データがありません。AIチャットから登録してみてください！")

# --- TAB 3: カロリー収支＆運動 ---
with tab3:
    st.header("🔥 カロリー収支（摂取 vs 総消費）")
    
    conn = get_connection()
    df_in = pd.read_sql_query("SELECT date, SUM(calories) as intake_cal FROM meals GROUP BY date", conn)
    df_ex = pd.read_sql_query("SELECT date, SUM(burned_calories) as exercise_cal FROM exercises GROUP BY date", conn)
    df_bmr = pd.read_sql_query("SELECT date, bmr FROM body_composition WHERE bmr IS NOT NULL", conn)
    conn.close()

    if not df_in.empty or not df_ex.empty:
        df_balance = pd.merge(df_in, df_ex, on='date', how='outer').fillna(0)
        
        # 各日付のBMRを結合（データがない日は最新のBMRを自動割り当て）
        if not df_bmr.empty:
            df_balance = pd.merge(df_balance, df_bmr, on='date', how='left')
            df_balance['bmr'] = df_balance['bmr'].fillna(latest_bmr)
        else:
            df_balance['bmr'] = latest_bmr

        df_balance['total_burn'] = df_balance['bmr'] + df_balance['exercise_cal']
        df_balance['net_balance'] = df_balance['intake_cal'] - df_balance['total_burn']
        df_balance = df_balance.sort_values('date')

        latest_b = df_balance.iloc[-1]
        st.subheader(f"⚖️ 最新日 ({latest_b['date']}) のカロリー収支")
        
        b1, b2, b3, b4 = st.columns(4)
        b1.metric("摂取カロリー", f"{latest_b['intake_cal']:.0f} kcal")
        b2.metric("基礎代謝 (タニタ参照)", f"{latest_b['bmr']:.0f} kcal")
        b3.metric("運動消費カロリー", f"{latest_b['exercise_cal']:.0f} kcal")
        b4.metric("カロリー収支 (摂取 - 総消費)", f"{latest_b['net_balance']:.0f} kcal", 
                  delta=f"{latest_b['net_balance']:.0f} kcal", delta_color="inverse")

        st.subheader("📈 摂取カロリー vs 総消費カロリー（基礎代謝 + 運動）")
        fig_bal = px.bar(df_balance, x='date', y=['intake_cal', 'total_burn'], barmode='group',
                         title="日別 カロリー比較 (kcal)", labels={'value': 'kcal', 'variable': '区分'})
        st.plotly_chart(fig_bal, use_container_width=True)

        st.subheader("🏋️ 登録された運動ログ一覧")
        conn = get_connection()
        df_ex_list = pd.read_sql_query("SELECT date, exercise_name, duration_min, burned_calories FROM exercises ORDER BY id DESC LIMIT 10", conn)
        conn.close()
        st.dataframe(df_ex_list, use_container_width=True)
    else:
        st.info("食事または運動のデータが登録されると、カロリー収支グラフが表示されます。")

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
            
            st.dataframe(df_raw.head(3))

            # タニタCSVの各カラム判別ロジック
            col_map = {}
            for c in df_raw.columns:
                c_str = str(c).lower()
                if "日付" in c_str or "date" in c_str or "測定日時" in c_str:
                    col_map["date"] = c
                elif "体重" in c_str or "weight" in c_str:
                    col_map["weight"] = c
                elif "体脂肪" in c_str or "fat" in c_str:
                    col_map["body_fat"] = c
                elif "筋肉" in c_str or "muscle" in c_str:
                    col_map["muscle_mass"] = c
                elif "基礎代謝" in c_str or "bmr" in c_str:
                    col_map["bmr"] = c

            if "date" in col_map and "weight" in col_map:
                conn = get_connection()
                c = conn.cursor()
                imported_count = 0
                for _, row in df_raw.iterrows():
                    d_val = str(row[col_map["date"]]).split(" ")[0]
                    w_val = float(row[col_map["weight"]]) if pd.notnull(row[col_map["weight"]]) else None
                    f_val = float(row[col_map["body_fat"]]) if "body_fat" in col_map and pd.notnull(row[col_map["body_fat"]]) else None
                    m_val = float(row[col_map["muscle_mass"]]) if "muscle_mass" in col_map and pd.notnull(row[col_map["muscle_mass"]]) else None
                    b_val = float(row[col_map["bmr"]]) if "bmr" in col_map and pd.notnull(row[col_map["bmr"]]) else None
                    
                    if d_val and w_val:
                        c.execute('''
                            INSERT OR REPLACE INTO body_composition (date, weight, body_fat, muscle_mass, bmr)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (d_val, w_val, f_val, m_val, b_val))
                        imported_count += 1
                conn.commit()
                conn.close()
                st.success(f"🎉 {imported_count}件の体組成データを保存しました！（基礎代謝も自動更新されました）")
                st.rerun()
        except Exception as e:
            st.error(f"ファイル処理エラー: {e}")

    st.divider()
    st.subheader("📈 体組成データの推移")
    conn = get_connection()
    df_body = pd.read_sql_query("SELECT * FROM body_composition ORDER BY date", conn)
    conn.close()

    if not df_body.empty:
        fig_weight = px.line(df_body, x='date', y=['weight', 'muscle_mass'], title="体重・筋肉量の推移 (kg)", markers=True)
        st.plotly_chart(fig_weight, use_container_width=True)
        
        if 'bmr' in df_body.columns and df_body['bmr'].notnull().any():
            fig_bmr = px.line(df_body, x='date', y='bmr', title="基礎代謝の推移 (kcal)", markers=True)
            st.plotly_chart(fig_bmr, use_container_width=True)
            
        if 'body_fat' in df_body.columns and df_body['body_fat'].notnull().any():
            fig_fat = px.line(df_body, x='date', y='body_fat', title="体脂肪率の推移 (%)", markers=True)
            st.plotly_chart(fig_fat, use_container_width=True)
    else:
        st.info("体組成データがまだありません。上のボタンからCSVをアップロードしてください。")

