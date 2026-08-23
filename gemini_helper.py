import os
import json
import io
import streamlit as st
import datetime
from google import genai
from google.genai import types

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

    # API呼び出し
    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
            )
        )
        return json.loads(response.text)

    except Exception as e:
        err_msg = str(e)
        # 429 RESOURCE_EXHAUSTED (利用枠上限超過) のハンドリング
        if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
            user_warning = (
                "⚠️ **Gemini APIの利用枠上限に達しました。**\n\n"
                "しばらく時間をおいてから再度お試しいただくか、Google AI Studioのクレジット残高をご確認ください。"
            )
            return {
                "action_type": "GENERAL_CHAT",
                "assistant_response": user_warning
            }

        # その他のエラーハンドリング
        st.error(f"Gemini API呼び出しエラー: {err_msg}")
        return {
            "action_type": "GENERAL_CHAT",
            "assistant_response": "申し訳ありません。一時的なエラーが発生したためレスポンスを取得できませんでした。"
        }
