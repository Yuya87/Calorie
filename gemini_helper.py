import os
import json
import io
import streamlit as st
from google import genai
from google.genai import types

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
    必ず以下のJSON構造のみを出力してください。
    {
      "action_type": "MEAL_LOG" | "EXERCISE_LOG" | "UPDATE_GOAL" | "GENERAL_CHAT",
      "assistant_response": "ユーザーへのアドバイスや返答メッセージ",
      "meal_data": {"food_name": str, "calories": float, "protein": float, "fat": float, "carbs": float, "alcohol_g": float},
      "exercise_data": {"exercise_name": str, "duration_min": float, "burned_calories": float},
      "goal_data": {"target_cal": float, "target_p": float, "target_f": float, "target_c": float}
    }
    """

    contents = []
    
    # 会話履歴とユーザーメッセージをテキスト化
    history_text = ""
    for msg in chat_history[-6:]:
        history_text += f"{msg['role']}: {msg['content']}\n"
    
    prompt = ""
    if history_text:
        prompt += f"【会話履歴】\n{history_text}\n"
    if user_text:
        prompt += f"【最新のユーザー入力】\n{user_text}"
        
    if prompt:
        contents.append(prompt)
        
    # 画像データを新SDKの型(types.Part)に安全に変換
    if image is not None:
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format=image.format or 'JPEG')
        img_bytes = img_byte_arr.getvalue()
        
        contents.append(
            types.Part.from_bytes(
                data=img_bytes,
                mime_type=f"image/{(image.format or 'jpeg').lower()}"
            )
        )

    if not contents:
        contents.append("こんにちは")

    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
        )
    )

    try:
        return json.loads(response.text)
    except Exception:
        return {
            "action_type": "GENERAL_CHAT",
            "assistant_response": response.text or "解析結果の読み込みに失敗しました。"
        }
