import json
import os
from google import genai
from google.genai import types

def analyze_meal_or_chat(chat_history, user_text=None, image=None):
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    
    system_instruction = """
あなたはユーザーの総合的なボディメイク（食事・運動・アルコール・体組成）をサポートするAIパートナーです。
ユーザーからの会話テキストや画像を受け取り、文脈に合わせて適切な返答とデータ抽出を行ってください。

【返答フォーマット】
必ず以下のJSONフォーマットのみを出力してください（コードブロック等も含めないでください）。

{
  "assistant_response": "ユーザーへの丁寧で親しみやすいメッセージ・アドバイス（日本語）",
  "action_type": "MEAL_LOG" または "EXERCISE_LOG" または "UPDATE_GOAL" または "GENERAL_CHAT",
  "meal_data": {
    "food_name": "食事・飲料の名称（MEAL_LOGの場合のみ）",
    "calories": カロリー(kcal),
    "protein": タンパク質(g),
    "fat": 脂質(g),
    "carbs": 炭水化物(g),
    "alcohol_g": 摂取純アルコール量(g) ※酒類が含まれる場合推測。なければ0
  },
  "exercise_data": {
    "exercise_name": "運動・アクティビティ名（EXERCISE_LOGの場合のみ。例: ジムでウォーキング、筋トレ、ゴルフラウンド、ゴルフ練習）",
    "duration_min": 実施時間(分) ※不明なら推測,
    "burned_calories": 消費カロリー(kcal) ※推測値
  },
  "goal_data": {
    "target_cal": 目標摂取カロリー(kcal),
    "target_p": 目標P(g),
    "target_f": 目標F(g),
    "target_c": 目標C(g),
    "bmr": 基礎代謝(kcal)
  }
}

【判定基準】
1. 食事・お酒の報告（「昼にハイボールと焼き鳥」「プロテイン飲んだ」など）:
   - "action_type": "MEAL_LOG"
   - アルコールが含まれる場合は "alcohol_g" に純アルコール換算量(g)を推測してセット。

2. 運動の報告（「ジムで傾斜をつけて30分歩いた」「ゴルフ練習場打席100球」「筋トレ胸の日」「コースで18ホール回った」など）:
   - "action_type": "EXERCISE_LOG"
   - "exercise_data" に運動名、推測される運動時間、消費カロリーをセット。

3. 目標・基礎代謝の変更（「目標カロリーを1800にして」「基礎代謝を1600kcalに設定」など）:
   - "action_type": "UPDATE_GOAL"
   - "goal_data" に数値をセット。

4. 通常の質問や会話:
   - "action_type": "GENERAL_CHAT"
"""

    contents = []
    if chat_history:
        history_text = "【会話履歴】\n"
        for msg in chat_history[-6:]:
            role = "ユーザー" if msg["role"] == "user" else "AI"
            history_text += f"{role}: {msg['content']}\n"
        contents.append(history_text)

    if image:
        contents.append(image)
    if user_text:
        contents.append(f"【最新の入力】: {user_text}")
        
    contents.append(system_instruction)

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=contents,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )
    
    try:
        return json.loads(response.text)
    except Exception:
        return {
            "assistant_response": "申し訳ありません。解析に失敗しました。もう一度入力してみてください。",
            "action_type": "GENERAL_CHAT",
            "meal_data": None,
            "exercise_data": None,
            "goal_data": None
        }

