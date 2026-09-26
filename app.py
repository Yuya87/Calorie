import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, date, timedelta
import json

# 内部モジュールのインポート
import firestore_db as db
import ai_services as ai

# ページ基本設定
st.set_page_config(
    page_title="AI Body Make & Habit Tracker",
    page_icon="🏋️‍♂️",
    layout="wide"
)

# ------------------------------------------------------------------------------
# セッション状態の初期化
# ------------------------------------------------------------------------------
if "selected_date" not in st.session_state:
    st.session_state["selected_date"] = date.today()

# ------------------------------------------------------------------------------
# サイドバー: 目標設定
# ------------------------------------------------------------------------------
st.sidebar.header("🎯 目標設定")
latest_goal = db.get_latest_user_goal()

if latest_goal:
    default_cal = float(latest_goal.get("target_cal", 2000))
    default_p = float(latest_goal.get("target_p", 150))
    default_f = float(latest_goal.get("target_f", 50))
    default_c = float(latest_goal.get("target_c", 200))
else:
    default_cal, default_p, default_f, default_c = 2000.0, 150.0, 50.0, 200.0

with st.sidebar.form("goals_form"):
    target_cal = st.number_input("目標カロリー (kcal)", value=default_cal, step=50.0)
    target_p = st.number_input("目標タンパク質 P (g)", value=default_p, step=5.0)
    target_f = st.number_input("目標脂質 F (g)", value=default_f, step=5.0)
    target_c = st.number_input("目標炭水化物 C (g)", value=default_c, step=5.0)
    
    submit_goal = st.form_submit_button("目標を更新")
    if submit_goal:
        db.save_user_goal(target_cal, target_p, target_f, target_c)
        st.sidebar.success("目標を更新しました！")
        st.rerun()

# ------------------------------------------------------------------------------
# メイン画面 タブ構成
# ------------------------------------------------------------------------------
st.title("🏋️‍♂️ AI Body Make & Habit Tracker")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📝 本日のデータ入力",
    "📊 日次サマリー＆KPI",
    "📈 習慣＆体組成の分析",
    "📊 過去1週間の推移",
    "⚙️ 設定"
])

# ==============================================================================
# TAB 1: 本日のデータ入力
# ==============================================================================
with tab1:
    st.subheader("📝 本日のデータ入力")
    
    # 日付選択
    target_date = st.date_input("記録対象日", value=st.session_state["selected_date"])
    st.session_state["selected_date"] = target_date
    date_str = target_date.strftime("%Y-%m-%d")
    weekday_str = ["月", "火", "水", "木", "金", "土", "日"][target_date.weekday()]
    st.info(f"選択中: {date_str} ({weekday_str})")

    st.markdown("---")
    
    # 1. 習慣化チェックイン
    st.markdown("### 🏋️ 1. 習慣化チェックイン")
    current_habit = db.get_daily_habit(date_str) or {}
    
    status_options = ["未記録", "目標達成", "一応やった", "未実施"]
    
    def_gym = current_habit.get("gym", "未記録")
    def_eng = current_habit.get("english", "未記録")
    def_rest = current_habit.get("rest_day", "未記録")
    def_memo = current_habit.get("memo", "")

    col_h1, col_h2, col_h3 = st.columns(3)
    with col_h1:
        gym_status = st.radio("🏋️ 筋トレ/運動", status_options, index=status_options.index(def_gym) if def_gym in status_options else 0, key="habit_gym")
    with col_h2:
        eng_status = st.radio("🇬🇧 英語学習", status_options, index=status_options.index(def_eng) if def_eng in status_options else 0, key="habit_eng")
    with col_h3:
        rest_status = st.radio("🍺 休肝日", status_options, index=status_options.index(def_rest) if def_rest in status_options else 0, key="habit_rest")
        
    habit_memo = st.text_input("習慣メモ", value=def_memo, placeholder="今日の習慣に関するひとこと")
    
    if st.button("習慣化チェックインを保存"):
        db.save_daily_habit(date_str, gym_status, eng_status, rest_status, habit_memo)
        st.success("習慣化チェックインを保存しました！")

    st.markdown("---")

    # 2. 食事ログの入力
    st.markdown("### 🥗 2. 食事ログの入力")
    
    # 辞書ルールの確認・登録アコーディオン
    with st.expander("📖 栄養辞書ルール（カスタム定義）の管理"):
        rules = db.get_user_rules()
        if rules:
            for r in rules:
                st.text(f"・{r.get('title')}: {r.get('detail')}")
        else:
            st.caption("登録されたルールはありません。")
            
        with st.form("add_rule_form"):
            rule_title = st.text_input("単語・料理名", placeholder="例: プロテイン1杯")
            rule_detail = st.text_input("計算ルール・仕様", placeholder="例: カロリー120kcal, タンパク質20g, 脂質1g, 炭水化物3g")
            if st.form_submit_button("辞書に追加"):
                if rule_title and rule_detail:
                    db.save_user_rule(rule_title, rule_detail)
                    st.success(f"『{rule_title}』を辞書に登録しました。")
                    st.rerun()

    meal_type = st.selectbox("食事種別", ["朝食", "昼食", "夕食", "間食", "不明"])
    meal_text = st.text_area("食事内容（AI解析テキスト）", placeholder="例: ラーメンと餃子を食べた。ビールも1杯飲んだ。")
    
    is_eating_out = st.checkbox("外食・会食フラグ")
    restaurant_name = ""
    dining_partners = ""
    eating_out_comment = ""
    if is_eating_out:
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            restaurant_name = st.text_input("店名・場所")
        with col_m2:
            dining_partners = st.text_input("同行者")
        eating_out_comment = st.text_input("外食メモ・評価")

    if st.button("AIで解析して食事ログを保存"):
        if meal_text:
            with st.spinner("Geminiが栄養素を解析中..."):
                dict_rules = db.get_user_rules()
                analysis = ai.analyze_meal_text(meal_text, dict_rules)
                
                # Firestoreへ保存
                db.save_meal_log(
                    date_str=date_str,
                    meal_type=meal_type,
                    food_name=analysis.get("food_name", meal_text),
                    calories=analysis.get("calories", 0.0),
                    protein=analysis.get("protein", 0.0),
                    fat=analysis.get("fat", 0.0),
                    carbs=analysis.get("carbs", 0.0),
                    alcohol_g=analysis.get("alcohol_g", 0.0),
                    is_eating_out=is_eating_out,
                    restaurant_name=restaurant_name,
                    dining_partners=dining_partners,
                    eating_out_comment=eating_out_comment
                )
                st.success("食事ログを解析・保存しました！")
                st.rerun()
        else:
            st.warning("食事内容を入力してください。")

    st.markdown("---")

    # 3. 運動ログの入力
    st.markdown("### 🏃 3. 運動ログの入力")
    
    if st.button("⚡ Quick: 傾斜ウォーキング 30分 (200kcal) を記録"):
        db.save_exercise_log(date_str, "傾斜ウォーキング", 30.0, 200.0)
        st.success("傾斜ウォーキングを記録しました！")
        st.rerun()
        
    exercise_text = st.text_input("運動内容（AI解析テキスト）", placeholder="例: ベンチプレス 45分、ジョギング 20分")
    if st.button("AIで解析して運動ログを保存"):
        if exercise_text:
            with st.spinner("Geminiが消費カロリーを解析中..."):
                analysis = ai.analyze_exercise_text(exercise_text)
                db.save_exercise_log(
                    date_str=date_str,
                    exercise_name=analysis.get("exercise_name", exercise_text),
                    duration_min=analysis.get("duration_min", 0.0),
                    burned_calories=analysis.get("burned_calories", 0.0)
                )
                st.success("運動ログを解析・保存しました！")
                st.rerun()

    st.markdown("---")

    # 4. 本日のジャーナリング
    st.markdown("### 📖 4. 本日のジャーナリング")
    current_journal = db.get_journal(date_str) or {}
    def_journal_note = current_journal.get("note", "")
    def_ai_feedback = current_journal.get("ai_feedback", "")
    
    journal_note = st.text_area("本日の振り返り・体調・気づき", value=def_journal_note)
    
    if st.button("振り返りを保存してAIフィードバックを取得"):
        if journal_note:
            with st.spinner("Geminiが本日の達成状況と振り返りを分析中..."):
                # 本日のデータ収集
                meals = db.get_meals_by_date(date_str)
                exercises = db.get_exercises_by_date(date_str)
                
                feedback = ai.generate_journal_feedback(
                    date_str=date_str,
                    journal_note=journal_note,
                    habit_data=current_habit,
                    meals_data=meals,
                    exercises_data=exercises
                )
                db.save_journal(date_str, journal_note, feedback)
                st.success("ジャーナリングとAIフィードバックを保存しました！")
                st.rerun()
        else:
            st.warning("振り返り内容を入力してください。")
            
    if def_ai_feedback:
        st.markdown("#### 🤖 AIからのフィードバック")
        st.info(def_ai_feedback)

    st.markdown("---")

    # 5. 体組成データの入力 (CSVアップロード対応)
    st.markdown("### ⚙️ 5. 体組成データの入力")
    
    uploaded_file = st.file_uploader("体組成計データ (CSV) をアップロード", type=["csv"])
    if uploaded_file is not None:
        try:
            df_csv = pd.read_csv(uploaded_file)
            st.write("プレビュー:", df_csv.head())
            if st.button("CSVデータをインポート"):
                # 想定フォーマット: date, weight, body_fat, muscle_mass, bmr
                for _, row in df_csv.iterrows():
                    d_str = str(row["date"])
                    w = float(row.get("weight", 0.0))
                    bf = float(row.get("body_fat", 0.0))
                    mm = float(row.get("muscle_mass", 0.0))
                    bmr = float(row.get("bmr", 0.0))
                    db.save_body_composition(d_str, w, bf, mm, bmr)
                st.success("CSVデータのインポートが完了しました！")
        except Exception as e:
            st.error(f"CSVの読み込みエラー: {e}")

# ==============================================================================
# TAB 2: 日次サマリー＆KPI
# ==============================================================================
with tab2:
    st.subheader("📊 日次サマリー＆KPI")
    
    summary_date = st.date_input("表示対象日", value=st.session_state["selected_date"], key="tab2_date")
    s_date_str = summary_date.strftime("%Y-%m-%d")
    
    meals = db.get_meals_by_date(s_date_str)
    exercises = db.get_exercises_by_date(s_date_str)
    habit = db.get_daily_habit(s_date_str) or {}
    
    # 栄養素計算
    total_cal = sum(m.get("calories", 0.0) for m in meals)
    total_p = sum(m.get("protein", 0.0) for m in meals)
    total_f = sum(m.get("fat", 0.0) for m in meals)
    total_c = sum(m.get("carbs", 0.0) for m in meals)
    total_burned = sum(e.get("burned_calories", 0.0) for e in exercises)
    
    col_k1, col_k2, col_k3, col_k4, col_k5 = st.columns(5)
    col_k1.metric("摂取カロリー", f"{total_cal:.0f} kcal", f"目標: {default_cal:.0f}")
    col_k2.metric("タンパク質 (P)", f"{total_p:.1f} g", f"目標: {default_p:.0f}")
    col_k3.metric("脂質 (F)", f"{total_f:.1f} g", f"目標: {default_f:.0f}")
    col_k4.metric("炭水化物 (C)", f"{total_c:.1f} g", f"目標: {default_c:.0f}")
    col_k5.metric("消費カロリー", f"{total_burned:.0f} kcal")
    
    st.markdown("---")
    st.markdown("### 習慣ステータス")
    col_sh1, col_sh2, col_sh3 = st.columns(3)
    col_sh1.write(f"🏋️ 運動: **{habit.get('gym', '未記録')}**")
    col_sh2.write(f"🇬🇧 英語: **{habit.get('english', '未記録')}**")
    col_sh3.write(f"🍺 休肝日: **{habit.get('rest_day', '未記録')}**")
    
    st.markdown("---")
    st.markdown("### 食事明細")
    
    if meals:
        df_meals = pd.DataFrame(meals)
        
        # ソート定義: 朝食 -> 昼食 -> 夕食 -> 間食 -> 不明
        type_order = {"朝食": 1, "昼食": 2, "夕食": 3, "間食": 4, "不明": 5}
        df_meals["order"] = df_meals["meal_type"].map(lambda x: type_order.get(x, 99))
        df_meals = df_meals.sort_values("order").drop(columns=["order"])
        
        for idx, row in df_meals.iterrows():
            col_m1, col_m2, col_m3, col_m4 = st.columns([2, 4, 2, 2])
            col_m1.write(f"**[{row.get('meal_type')}]**")
            col_m2.write(f"{row.get('food_name')} ({row.get('calories', 0):.0f} kcal)")
            
            # インライン編集ポップオーバー
            with col_m3:
                with st.popover("編集"):
                    with st.form(f"edit_meal_{row['id']}"):
                        edit_type = st.selectbox("種別", ["朝食", "昼食", "夕食", "間食", "不明"], index=["朝食", "昼食", "夕食", "間食", "不明"].index(row.get("meal_type", "不明")))
                        edit_name = st.text_input("品目名", value=row.get("food_name", ""))
                        edit_cal = st.number_input("カロリー", value=float(row.get("calories", 0.0)))
                        edit_p = st.number_input("P (g)", value=float(row.get("protein", 0.0)))
                        edit_f = st.number_input("F (g)", value=float(row.get("fat", 0.0)))
                        edit_c = st.number_input("C (g)", value=float(row.get("carbs", 0.0)))
                        
                        if st.form_submit_button("保存"):
                            db.update_meal_log(row["id"], {
                                "meal_type": edit_type,
                                "food_name": edit_name,
                                "calories": edit_cal,
                                "protein": edit_p,
                                "fat": edit_f,
                                "carbs": edit_c
                            })
                            st.success("更新しました。")
                            st.rerun()
                            
            # 削除ボタン
            with col_m4:
                if st.button("削除", key=f"del_meal_{row['id']}"):
                    db.delete_meal_log(row["id"])
                    st.success("削除しました。")
                    st.rerun()
    else:
        st.caption("本日の食事ログはありません。")

# ==============================================================================
# TAB 3: 習慣＆体組成の分析
# ==============================================================================
with tab3:
    st.subheader("📈 習慣＆体組成の分析")
    
    # 過去30日間の習慣チェックインヒートマップ
    st.markdown("### 過去30日間の習慣達成ヒートマップ")
    
    today = date.today()
    past_30_days = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(29, -1, -1)]
    
    habits_data = db.get_habits_range(past_30_days[0], past_30_days[-1])
    habit_dict = {h["date"]: h for h in habits_data}
    
    score_map = {"目標達成": 3, "一応やった": 2, "未実施": 1, "未記録": 0}
    
    gym_scores = []
    eng_scores = []
    rest_scores = []
    
    for d in past_30_days:
        h = habit_dict.get(d, {})
        gym_scores.append(score_map.get(h.get("gym"), 0))
        eng_scores.append(score_map.get(h.get("english"), 0))
        rest_scores.append(score_map.get(h.get("rest_day"), 0))
        
    df_heatmap = pd.DataFrame([gym_scores, eng_scores, rest_scores], 
                              index=["運動", "英語学習", "休肝日"], 
                              columns=past_30_days)
    
    # Plotly imshow で正方形ヒートマップの作成
    fig_heat = px.imshow(
        df_heatmap,
        labels=dict(x="日付", y="習慣", color="達成度"),
        x=past_30_days,
        y=["運動", "英語学習", "休肝日"],
        color_continuous_scale=["#ebedf0", "#c6e48b", "#7bc96f", "#239a3b"],
        aspect="equal"  # アスペクト比の均等設定
    )
    
    # セルを完璧な正方形に固定・レイアウト最適化
    fig_heat.update_yaxes(scaleanchor="x", scaleratio=1)
    fig_heat.update_layout(
        xaxis=dict(tickangle=-45, showgrid=False),
        yaxis=dict(showgrid=False),
        coloraxis_showscale=False,
        margin=dict(l=20, r=20, t=30, b=30),
        autosize=True
    )
    
    st.plotly_chart(fig_heat, use_container_width=True)
    
    st.markdown("---")
    st.markdown("### 体組成データの推移 (過去30日間)")
    
    body_data = db.get_body_comp_range(past_30_days[0], past_30_days[-1])
    if body_data:
        df_body = pd.DataFrame(body_data).sort_values("date")
        
        # ※ 体重は非表示にし、体脂肪率・体脂肪量・骨格筋量を表示
        if "weight" in df_body.columns and "body_fat" in df_body.columns:
            df_body["fat_mass"] = df_body["weight"] * (df_body["body_fat"] / 100.0)
            
        fig_body = px.line(
            df_body,
            x="date",
            y=[c for c in ["body_fat", "fat_mass", "muscle_mass"] if c in df_body.columns],
            markers=True,
            title="体組成推移（体脂肪率 % / 体脂肪量 kg / 骨格筋量 kg）"
        )
        st.plotly_chart(fig_body, use_container_width=True)
    else:
        st.caption("過去30日間の体組成データがありません。")

# ==============================================================================
# TAB 4: 過去1週間の推移
# ==============================================================================
with tab4:
    st.subheader("📊 過去1週間の推移")
    
    past_7_days = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]
    
    daily_summaries = []
    for d in past_7_days:
        d_meals = db.get_meals_by_date(d)
        c_cal = sum(m.get("calories", 0.0) for m in d_meals)
        c_p = sum(m.get("protein", 0.0) for m in d_meals)
        c_f = sum(m.get("fat", 0.0) for m in d_meals)
        c_c = sum(m.get("carbs", 0.0) for m in d_meals)
        daily_summaries.append({
            "date": d,
            "calories": c_cal,
            "protein": c_p,
            "fat": c_f,
            "carbs": c_c
        })
        
    df_7days = pd.DataFrame(daily_summaries)
    
    # 摂取カロリー推移
    fig_cal = px.bar(df_7days, x="date", y="calories", title="過去7日間の合計摂取カロリー (kcal)")
    fig_cal.add_hline(y=default_cal, line_dash="dash", line_color="red", annotation_text="目標カロリー")
    st.plotly_chart(fig_cal, use_container_width=True)
    
    # PFC推移
    fig_pfc = px.line(df_7days, x="date", y=["protein", "fat", "carbs"], markers=True, title="過去7日間のPFC推移 (g)")
    fig_pfc.add_hline(y=default_p, line_dash="dash", line_color="blue", annotation_text="目標P")
    fig_pfc.add_hline(y=default_f, line_dash="dash", line_color="green", annotation_text="目標F")
    fig_pfc.add_hline(y=default_c, line_dash="dash", line_color="orange", annotation_text="目標C")
    st.plotly_chart(fig_pfc, use_container_width=True)

# ==============================================================================
# TAB 5: 設定
# ==============================================================================
with tab5:
    st.subheader("⚙️ 設定 & ヘルプ")
    st.write("・**目標設定**: サイドバーより各目標数値をいつでも変更可能です。")
    st.write("・**データベース**: Google Cloud Firestore に接続されています。")
    st.write("・**AIモデル**: Gemini (`gemini-3.6-flash`) を使用しています。")
