import os
import json
import io
import streamlit as st
from google import genai
from google.genai import types

def get_client():
    # secrets または os.environ から取得し、余計な空白を除去
    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY が設定されていません。StreamlitのSecretsを確認してください。")
    return genai.Client(api_key=api_key.strip())

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
    
    # 会話履歴をテキスト化
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
        
    # 画像の変換処理
    if image is not None:
        try:
            img_byte_arr = io.BytesIO()
            # フォーマットが不明な場合はPNGで保存
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

    # API呼び出し
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
            )
        )
        return json.loads(response.text)
        
    except Exception as e:
        # 詳細なエラーメッセージを表示して原因特定を容易にする
        st.error(f"Gemini API呼び出しエラー: {e}")
        return {
            "action_type": "GENERAL_CHAT",
            "assistant_response": "申し訳ありません。エラーが発生したためレスポンスを取得できませんでした。"
        }
