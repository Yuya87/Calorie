import os
import json
import io
import datetime
import pandas as pd
import plotly.express as px
import streamlit as st
from google import genai
from google.genai import types

# ------------------------------------------------------------------------------
# 1. Page Config & CSS (タイトルの文字サイズ調整)
# ------------------------------------------------------------------------------
st.set_page_config(page_title="AI Body Make & Tracker", layout="wide")

# タイトルやヘッダーの文字サイズをコンパクトにするCSS
st.markdown("""
    <style>
    /* メインタイトルのフォントサイズ調整 */
    h1 {
        font-size: 1.8rem !important;
        padding-top: 0.5rem !important;
        padding-bottom: 0.5rem !important;
    }
    /* サブタイトルのフォントサイズ調整 */
    h2 {
        font-size: 1.4rem !important;
    }
    h3 {
        font-size: 1.1rem !important;
    }
    /* コンパクト表示用のカードスタイル */
    .summary-card {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 12px;
        margin-bottom: 10px;
        border-left: 4px solid #4CAF50;
    }
    </style>
""", unsafe_allow_html=True)


# ------------------------------------------------------------------------------
# 2. Gemini API 連携ロジック (gemini_helper.py)
# ------------------------------------------------------------------------------
def get_client():
    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY が設定されていません。StreamlitのSecretsを確認してください。")
    return genai.Client(api_key=api_key.strip())

def analyze_meal_or_chat(chat_history, user_text=None, image=None, existing_logs=None):
    client = get_client()
    today_str = datetime.date.today().strftime('%Y-%m-%d')

    system_instruction = f"""
    あなたは親切で高度なボディメイク・栄養アドバイザーAIです。
    本日の日付は 【 {today_str} 】 です。
    ユーザーからの発言や画像をもとに、以下のルールでJSONレスポンスを生成してください。

    【最重要出力ルール】
    指定された純粋なJSON構造のみを出力してください。
    JSON構造の外側に、思考プロセス、前置き、後置き、説明テキスト、コードブロック記号（```json 等）を含めることは厳禁です。
    ユーザーへのメッセージやアドバイスは、必ずJSON内部の assistant_response フィールドの中に格納してください。

    【日付判定ルール】
    - ユーザーが「昨日」「おととい」「8月20日」など日付を指定している場合は、その日付を YYYY-MM-DD 形式で target_date に格納してください。
    - 特に日付の指定がない場合や「今日」「さっき」等の場合は、本日の日付 ({today_str}) を target_date に設定してください。

    【アクション判定ルール】
    1. 食事や飲酒の新規記録の場合:
       - action_type: "MEAL_LOG"
       - meal_data に food_name, calories, protein, fat, carbs, alcohol_g (純アルコール量) を格納。
    2. 運動やアクティビティの新規記録の場合:
       - action_type: "EXERCISE_LOG"
       - exercise_data に exercise_name, duration_min, burned_calories を格納。
    3. 既存のログの修正の場合 (既存ログ一覧を参照し、該当する doc_id を指定):
       - action_type: "UPDATE_LOG"
       - target_collection: "meals" または "exercises"
       - target_doc_id: 修正対象のドキュメントID (str)
       - meal_data または exercise_data に修正後の数値を格納。
    4. 既存のログの削除の場合 (既存ログ一覧を参照し、該当する doc_id を指定):
       - action_type: "DELETE_LOG"
       - target_collection: "meals" または "exercises"
       - target_doc_id: 削除対象のドキュメントID (str)
    5. 目標カロリーやPFCの変更希望の場合:
       - action_type: "UPDATE_GOAL"
       - goal_data に target_cal, target_p, target_f, target_c を格納。
    6. 単なる質問や雑談の場合:
       - action_type: "GENERAL_CHAT"

    【出力JSONフォーマット】
    必ず以下のJSON構造のみを出力してください。
    {{
      "action_type": "MEAL_LOG" | "EXERCISE_LOG" | "UPDATE_LOG" | "DELETE_LOG" | "UPDATE_GOAL" | "GENERAL_CHAT",
      "target_date": "YYYY-MM-DD",
      "target_collection": "meals" | "exercises" | null,
      "target_doc_id": "文字列のDocID" | null,
      "assistant_response": "ユーザーへのアドバイスや完了通知メッセージ",
      "meal_data": {{"food_name": str, "calories": float, "protein": float, "fat": float, "carbs": float, "alcohol_g": float}},
      "exercise_data": {{"exercise_name": str, "duration_min": float, "burned_calories": float}},
      "goal_data": {{"target_cal": float, "target_p": float, "target_f": float, "target_c": float}}
    }}
    """

    contents = []

    # 会話履歴
    history_text = ""
    for msg in chat_history[-6:]:
        history_text += f"{msg['role']}: {msg['content']}\n"

    # 既存ログ情報の付与（修正・削除の判別用）
    logs_context = ""
    if existing_logs:
        logs_context = f"【現在登録されている直近ログ一覧】\n{json.dumps(existing_logs, ensure_ascii=False, indent=2)}\n"

    prompt = ""
    if logs_context:
        prompt += logs_context
    if history_text:
        prompt += f"【会話履歴】\n{history_text}\n"
    if user_text:
        prompt += f"【最新のユーザー入力】\n{user_text}"

    if prompt:
        contents.append(prompt)

    # 画像の変換処理
    if image is not None:
        try:
            img_byte_arr = io.BytesIO()
            img_format = image.format if image.format else 'PNG'
            image.save(img_byte_arr, format=img_format)
            img_bytes = img_byte_arr.getvalue()

            contents.append(
                types.Part.from_bytes(
                    data=img_bytes,
                    mime_type=f"image/{img_format.lower()}"
                )
            )
        except Exception as e:
            st.warning(f"画像の処理中にエラーが発生しました: {e}")

    if not contents:
        contents.append("こんにちは")

    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                thinking_config=types.ThinkingConfig(
                    thinking_budget=1
                )
            )
        )
        return json.loads(response.text)

    except Exception as e:
        err_msg = str(e)
        if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
            user_warning = (
                "⚠️ **Gemini APIの利用枠上限に達しました。**\n\n"
                "しばらく時間をおいてから再度お試しいただくか、Google AI Studioのクレジット残高をご確認ください。"
            )
            return {
                "action_type": "GENERAL_CHAT",
                "assistant_response": user_warning
            }

        st.error(f"Gemini API呼び出しエラー: {err_msg}")
        return {
            "action_type": "GENERAL_CHAT",
            "assistant_response": "申し訳ありません。一時的なエラーが発生したためレスポンスを取得できませんでした。"
        }


# ------------------------------------------------------------------------------
# 3. メインUIコンポーネント (栄養・アルコール管理タブ)
# ------------------------------------------------------------------------------
st.title("💪 AI ボディメイク & 体組成トラッカー")

tabs = st.tabs(["栄養・アルコール管理", "運動・体組成", "チャットサポート"])

with tabs[0]:
    # サンプルデータ / Firestoreから取得する構造を想定
    today = datetime.date.today()
    dates = [(today - datetime.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]

    # ダミーデータ構成 (実際のアプリではFirestoreから取得)
    df_daily = pd.DataFrame({
        "date": dates,
        "Protein (g)": [120, 135, 110, 140, 125, 130, 105],
        "Fat (g)": [50, 45, 60, 55, 40, 50, 45],
        "Carbs (g)": [200, 180, 220, 190, 210, 175, 160],
        "Alcohol (g)": [0, 15, 0, 30, 0, 0, 20],
        "Calories (kcal)": [1730, 1665, 1860, 1810, 1700, 1670, 1465]
    })

    target_goals = {"target_cal": 2000, "target_p": 140, "target_f": 50, "target_c": 200}

    # --------------------------------------------------------------------------
    # A. 摂取カロリー・PFC達成状況 (コンパクト表示)
    # --------------------------------------------------------------------------
    st.subheader("🎯 本日の達成状況")
    
    # 今日の数値を取得 (最新日付)
    today_data = df_daily.iloc[-1]

    col_cal, col_p, col_f, col_c = st.columns(4)

    with col_cal:
        cal_pct = min(1.0, today_data["Calories (kcal)"] / target_goals["target_cal"])
        st.metric(label="カロリー", value=f"{int(today_data['Calories (kcal)'])} kcal", delta=f"{int(today_data['Calories (kcal)'] - target_goals['target_cal'])} kcal")
        st.progress(cal_pct, text=f"目標: {target_goals['target_cal']} kcal")

    with col_p:
        p_pct = min(1.0, today_data["Protein (g)"] / target_goals["target_p"])
        st.metric(label="P (タンパク質)", value=f"{int(today_data['Protein (g)'])} g", delta=f"{int(today_data['Protein (g)'] - target_goals['target_p'])} g")
        st.progress(p_pct, text=f"目標: {target_goals['target_p']}g")

    with col_f:
        f_pct = min(1.0, today_data["Fat (g)"] / target_goals["target_f"])
        st.metric(label="F (脂質)", value=f"{int(today_data['Fat (g)'])} g", delta=f"{int(today_data['Fat (g)'] - target_goals['target_f'])} g")
        st.progress(f_pct, text=f"目標: {target_goals['target_f']}g")

    with col_c:
        c_pct = min(1.0, today_data["Carbs (g)"] / target_goals["target_c"])
        st.metric(label="C (炭水化物)", value=f"{int(today_data['Carbs (g)'])} g", delta=f"{int(today_data['Carbs (g)'] - target_goals['target_c'])} g")
        st.progress(c_pct, text=f"目標: {target_goals['target_c']}g")

    st.markdown("---")

    # --------------------------------------------------------------------------
    # B. PFC & アルコール推移 (1つの折れ線グラフで比較)
    # --------------------------------------------------------------------------
    st.subheader("📈 栄養・アルコール推移 (過去7日間)")

    # Plotly用にロングフォーマットに変換
    df_melted = df_daily.melt(
        id_vars=["date"], 
        value_vars=["Protein (g)", "Fat (g)", "Carbs (g)", "Alcohol (g)"],
        var_name="栄養要素", 
        value_name="量 (g)"
    )

    fig = px.line(
        df_melted, 
        x="date", 
        y="量 (g)", 
        color="栄養要素",
        markers=True,
        color_discrete_map={
            "Protein (g)": "#FF4B4B",
            "Fat (g)": "#FFAA00",
            "Carbs (g)": "#00B4D8",
            "Alcohol (g)": "#9D4EDD"
        }
    )

    fig.update_layout(
        xaxis_title=None,
        yaxis_title="グラム (g)",
        legend_title=None,
        margin=dict(l=20, r=20, t=20, b=20),
        height=320,
        hovermode="x unified"
    )

    st.plotly_chart(fig, use_container_width=True)

    # --------------------------------------------------------------------------
    # C. 過去3日分の運動・食事サマリ
    # --------------------------------------------------------------------------
    st.subheader("📋 直近3日間の活動サマリ")

    # サンプルログデータ（Firestore連携用）
    dummy_recent_logs = {
        dates[-1]: {
            "meals": ["鶏胸肉のサラダ (320kcal, P:40g)", "プロテインシェイク (120kcal, P:20g)", "ハイボール 1杯 (100kcal, Alc:10g)"],
            "exercises": ["ランニング 30分 (250kcal消費)"]
        },
        dates[-2]: {
            "meals": ["玄米定食 (600kcal)", "鮭の塩焼き (250kcal)", "ギリシャヨーグルト (100kcal)"],
            "exercises": ["筋トレ (胸・肩) 45分 (180kcal消費)"]
        },
        dates[-3]: {
            "meals": ["プロテイン (120kcal)", "ベースフードパン (250kcal)", "蒸し鶏ともやし (200kcal)"],
            "exercises": ["休養日"]
        }
    }

    # 過去3日分（最新から降順）でループ処理
    last_3_days = dates[-1:-4:-1]

    cols_3days = st.columns(3)
    for idx, day_str in enumerate(last_3_days):
        with cols_3days[idx]:
            day_label = "本日" if idx == 0 else ("昨日" if idx == 1 else "一昨日")
            st.markdown(f"**📅 {day_str} ({day_label})**")

            log_data = dummy_recent_logs.get(day_str, {"meals": [], "exercises": []})

            with st.expander("🥗 食事内容", expanded=True):
                if log_data["meals"]:
                    for meal in log_data["meals"]:
                        st.markdown(f"- {meal}")
                else:
                    st.caption("記録なし")

            with st.expander("🏃 運動内容", expanded=True):
                if log_data["exercises"]:
                    for ex in log_data["exercises"]:
                        st.markdown(f"- {ex}")
                else:
                    st.caption("記録なし")
