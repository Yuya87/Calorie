import os
import json
import datetime
import pandas as pd
from PIL import Image
from google import genai
from google.genai import types

# ------------------------------------------------------------------------------
# システムプロンプト（Geminiの役割・レスポンスフォーマット・判定ルール定義）
# ------------------------------------------------------------------------------
SYSTEM_INSTRUCTION = """
あなたはAIボディメイク＆栄養管理のアシスタントです。
ユーザーとの会話テキストや画像から、意図（食事記録、運動記録、ログの更新、削除、目標変更、雑談など）を判定し、適切なアクションとレスポンスを生成してください。

【重要：ユーザー定義の前提ルール・レシピ仕様の優先適用】
入力データ内に「【ユーザー定義の前提ルール・レシピ仕様】」が含まれている場合は、通常の一般的栄養数値よりも**そのルールを最優先して**栄養計算を行ってください。
（例：「無水カレー」→ ノンオイル・ささみ/胸肉使用・スパイス仕込みのヘルシー仕様として計算）
（例：「ゆで卵」→ 黄身を食べず白身のみ食べる指定がある場合は、白身分の栄養素のみで計算）

【返釈レスポンスのフォーマット】
必ず以下のJSON形式でのみレスポンスを出力してください。余計な解説文やMarkdownタグ（```json ... ```等）は一切含めないでください。

{
  "action_type": "MEAL_LOG" | "EXERCISE_LOG" | "UPDATE_LOG" | "DELETE_LOG" | "UPDATE_GOAL" | "GENERAL_CHAT",
  "target_date": "YYYY-MM-DD",  // ユーザーが日付を指定した場合（「昨日の夜」「8/10」など）はその日付。指定がなければnull
  "assistant_response": "ユーザーへの親切で前向きな返答メッセージ",
  
  // MEAL_LOG（食事追加）または UPDATE_LOG（食事修正）の場合のみ設定
  "meal_data": {
    "food_name": "料理・食材名",
    "calories": 350.0,
    "protein": 30.0,
    "fat": 5.0,
    "carbs": 40.0,
    "alcohol_g": 0.0 // アルコールが含まれる場合は純アルコール量(g)を計算して設定
  },
  
  // EXERCISE_LOG（運動追加）または UPDATE_LOG（運動修正）の場合のみ設定
  "exercise_data": {
    "exercise_name": "運動名",
    "duration_min": 30.0,
    "burned_calories": 150.0
  },
  
  // UPDATE_LOG または DELETE_LOG の場合のみ設定（過去ログ文脈から合致するdoc_idを特定）
  "target_doc_id": "FirestoreのドキュメントID文字列",
  "target_collection": "meals" | "exercises",
  
  // UPDATE_GOAL（目標変更）の場合のみ設定
  "goal_data": {
    "target_cal": 2000.0,
    "target_p": 120.0,
    "target_f": 50.0,
    "target_c": 200.0
  }
}

【判定・挙動ルール】
1. 日付指定の解釈: 「昨日」「一昨日の昼」「8/15」などの表現から正確な YYYY-MM-DD を算出して `target_date` に設定してください。指定がない場合は null（呼び出し側で本日日付が補完されます）にしてください。
2. 削除・修正の特定: 提供された「過去のログ一覧（doc_id付き）」を参照し、ユーザーが削除・修正したがっている記録の `doc_id` と `collection` を正確に特定してください。
3. 栄養素の推定: 前提ルールを考慮した上で、現実的なPFCバランスおよびカロリーを推定してください。アルコールを含む飲料（ビール、ハイボール等）の場合は `alcohol_g` に純アルコール量(g)（度数% × 量ml × 0.8 / 100）を算出して設定してください。
"""

def analyze_meal_or_chat(messages_history, user_text, image=None, existing_logs=None):
    """
    Gemini 2.5 Flash を使用してユーザーの入力を解析し、JSON形式で結果を返す関数
    """
    # Streamlit secrets または環境変数からAPIキーを取得
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        try:
            import streamlit as st
            api_key = st.secrets["GEMINI_API_KEY"]
        except Exception:
            pass

    client = genai.Client(api_key=api_key)

    # 1. 過去ログおよび前提ルールの文脈抽出
    context_str = ""
    user_rules_str = ""

    if existing_logs:
        logs_summary = []
        for log in existing_logs:
            # 前提ルールテキストの抽出
            if "system_user_rules" in log:
                user_rules_str = log["system_user_rules"]
            else:
                doc_id = log.get("doc_id", "N/A")
                coll = log.get("collection", "N/A")
                date = log.get("date", "N/A")
                if coll == "meals":
                    name = log.get("food_name", "食事")
                    cal = log.get("calories", 0)
                    logs_summary.append(f"- [ID: {doc_id} / 種別: meals / 日付: {date}] {name} ({cal}kcal)")
                elif coll == "exercises":
                    name = log.get("exercise_name", "運動")
                    burn = log.get("burned_calories", 0)
                    logs_summary.append(f"- [ID: {doc_id} / 種別: exercises / 日付: {date}] {name} ({burn}kcal消費)")

        if logs_summary:
            context_str += "\n【参照可能な直近の登録ログ一覧】\n" + "\n".join(logs_summary)

    # ユーザー定義ルールが存在する場合は文脈の最前列に追加
    if user_rules_str:
        context_str = user_rules_str + "\n" + context_str

    # 2. 会話履歴のプロンプト化
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    prompt_content = [
        f"本日の日付: {today_str}\n",
        context_str,
        "\n【これまでの会話の流れ】\n"
    ]

    for msg in messages_history[-6:]:  # 直近の会話数件を文脈として保持
        role = "ユーザー" if msg["role"] == "user" else "アシスタント"
        prompt_content.append(f"{role}: {msg['content']}\n")

    prompt_content.append(f"ユーザーの最新の入力: {user_text}\n")

    # 画像が添付されている場合は入力に追加
    if image:
        prompt_content.append(image)

    # 3. Gemini API 呼び出し
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt_content,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                temperature=0.2
            )
        )

        # JSONレスポンスのパース
        res_json = json.loads(response.text)
        return res_json

    except Exception as e:
        # エラー発生時のフォールバック
        return {
            "action_type": "GENERAL_CHAT",
            "target_date": None,
            "assistant_response": f"申し訳ありません、解析中にエラーが発生しました。({str(e)})"
        }
