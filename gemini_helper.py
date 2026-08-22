import os
import json
from google import genai
from google.genai import types

import streamlit as st

# Streamlit Secrets から API キーを読み込む
api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

def get_client():
    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY が設定されていません。StreamlitのSecretsを確認してください。")
    return genai.Client(api_key=api_key)

def analyze_meal_or_chat(chat_history, user_text=None, image=None):
    client = get_client()
    
    system_instruction = """
    あなたは親切で高度なボディメイク・栄養アドバイザーAIです。
    ユーザーからの発言や画像をもとに、以下のルールでJSONレスポンスを生成してください。

    【アクション判定ルール】
    1. 食事や飲酒の報告の場合:
       - action_type: "MEAL_LOG"
       - meal_data に food_name, calories, protein, fat, carbs, alcohol_g (純アルコール量) を解析・推定して格納。
    2. 運動やアクティビティの報告の場合:
       - action_type: "EXERCISE_LOG"
       - exercise_data に exercise_name, duration_min, burned_calories を解析・推定して格納。
    3. 目標カロリーやPFCの変更希望の場合:
       - action_type: "UPDATE_GOAL"
       - goal_data に target_cal, target_p, target_f, target_c を格納。
    4. 単なる質問や雑談の場合:
       - action_type: "GENERAL_CHAT"

    【出力JSONフォーマット】
    必ず以下のJSON構造のみを出力してください（Markdownのコードブロックは不要）。
    {
      "action_type": "MEAL_LOG" | "EXERCISE_LOG" | "UPDATE_GOAL" | "GENERAL_CHAT",
      "assistant_response": "ユーザーへのアドバイスや返答メッセージ",
      "meal_data": {"food_name": str, "calories": float, "protein": float, "fat": float, "carbs": float, "alcohol_g": float},
      "exercise_data": {"exercise_name": str, "duration_min": float, "burned_calories": float},
      "goal_data": {"target_cal": float, "target_p": float, "target_f": float, "target_c": float}
    }
    """

    # 送信用のリストを綺麗に作成
    contents = []
    
    # システムプロンプト（指示文）を先頭に入れる
    contents.append(system_instruction)
    
    # 過去の会話履歴をテキストとしてまとめる
    history_text = ""
    for msg in chat_history[-6:]:
        history_text += f"{msg['role']}: {msg['content']}\n"
    if history_text:
        contents.append(f"【会話履歴】\n{history_text}")
    
    # 今回のユーザー入力
    if user_text:
        contents.append(f"user: {user_text}")
    if image:
        contents.append(image)

    # API呼び出し
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=contents,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        )
    )
