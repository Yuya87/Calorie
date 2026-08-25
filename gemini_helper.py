import os
import json
import re
import datetime
from google import genai
from google.genai import types

# ------------------------------------------------------------------------------
# システムプロンプト（Geminiの役割・レスポンスフォーマット・判定ルール定義）
# ------------------------------------------------------------------------------
SYSTEM_INSTRUCTION = """
あなたはAIボディメイク＆栄養管理アシスタントです。
入力テキストや画像から意図（食事記録、運動記録、ログ更新/削除、目標変更、雑談など）を判定し、適切なアクションとValidなJSONレスポンスを生成してください。

【重要：JSON出力ルール】
- 必ずJSONフォーマットのみを出力してください。
- Markdownのコードブロック（```json）や解説文章は一切含めないでください。
- 文字列フィールド内でダブルクォーテーションを使う場合は必ずエスケープ (\\") してください。
- 各文字列値の中で意図しない改行文字（CR/LF）を入れないでください。

【前提ルール・レシピ仕様の最優先適用】
「【ユーザー定義の前提ルール・レシピ仕様】」が含まれる場合は、通常の数値よりそのルールを最優先して計算してください（例: 無水カレー=ノンオイル・胸肉仕様、ゆで卵=白身のみ等）。

【複数データ対応】
1回の入力に複数の記録（朝・昼・夕食、複数のアルコール・運動など）が含まれる場合は、漏れなくすべて `items` 配列内にまとめて抽出してください。

【出力JSONフォーマット】
{
  "action_type": "MEAL_LOG" | "EXERCISE_LOG" | "UPDATE_LOG" | "DELETE_LOG" | "UPDATE_GOAL" | "GENERAL_CHAT",
  "target_date": "YYYY-MM-DD",
  "assistant_response": "ユーザーへの返答メッセージ（登録内容や修正の確認、聞き返し等）",
  "meal_data": {
    "items": [
      {
        "food_name": "料理・食材名",
        "calories": 0.0,
        "protein": 0.0,
        "fat": 0.0,
        "carbs": 0.0,
        "alcohol_g": 0.0
      }
    ]
  },
  "exercise_data": {
    "items": [
      {
        "exercise_name": "運動名",
        "duration_min": 0.0,
        "burned_calories": 0.0
      }
    ]
  },
  "target_doc_id": null,
  "target_collection": null,
  "goal_data": null
}

【判定ルール】
1. 日付: 指定があれば YYYY-MM-DD を算出して `target_date` に設定。無ければ null。
2. 明示的数値: ユーザーが「約34kcal」「P 7.2g」等と記載している場合はその数値を優先。
3. ログの修正・削除:
   - 「直近ログ一覧」から該当する `doc_id` と `collection` (`meals` または `exercises`) を特定して `UPDATE_LOG` / `DELETE_LOG` を返します。
   - 日付を修正する指示（例: 「昨日のカレーを今日に変更して」「さっきの食事を8/20にして」等）の場合、`target_date` に移動後の日付を設定し、対象の `target_doc_id` と `target_collection` を指定してください。
   - 変更・削除対象が複数あったり特定できない場合は、勝手に決めずに `action_type`: "GENERAL_CHAT" として「どのログ（日付や料理名）を変更しますか？」と確認を求めてください。
4. アルコール: ビールやハイボール等の純アルコール量(g) = 度数% × 量ml × 0.8 / 100 を算出して `alcohol_g` に設定。
"""

def analyze_meal_or_chat(messages_history, user_text, image=None, existing_logs=None):
    """
    Gemini 3.6 Flash を使用してユーザーの入力を解析し、JSON形式で結果を返す関数
    """
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
        for log in existing_logs[-8:]:
            if "system_user_rules" in log:
                user_rules_str = log["system_user_rules"]
            else:
                doc_id = log.get("doc_id", "N/A")
                coll = log.get("collection", "N/A")
                date = log.get("date", "N/A")
                if coll == "meals":
                    name = log.get("food_name", "食事")
                    cal = log.get("calories", 0)
                    logs_summary.append(f"- [ID:{doc_id} / Collection:{coll} / Date:{date}] {name} ({cal}kcal)")
                elif coll == "exercises":
                    name = log.get("exercise_name", "運動")
                    burn = log.get("burned_calories", 0)
                    logs_summary.append(f"- [ID:{doc_id} / Collection:{coll} / Date:{date}] {name} ({burn}kcal)")

        if logs_summary:
            context_str += "\n【参照可能な直近ログ一覧】\n" + "\n".join(logs_summary)

    if user_rules_str:
        context_str = user_rules_str + "\n" + context_str

    # 2. プロンプト生成
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    prompt_content = [
        f"本日: {today_str}\n",
        context_str,
        "\n【会話履歴】\n"
    ]

    for msg in messages_history[-4:]:
        role = "ユーザー" if msg["role"] == "user" else "アシスタント"
        prompt_content.append(f"{role}: {msg['content']}\n")

    prompt_content.append(f"ユーザー最新入力: {user_text}\n")

    if image:
        prompt_content.append(image)

    # 3. Gemini API 呼び出し
    try:
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt_content,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                temperature=0.1,
                max_output_tokens=1500
            )
        )

        raw_text = response.text.strip()
        
        # 不要なマークダウンコードブロックのクリーンアップ
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.IGNORECASE)
            raw_text = re.sub(r"\s*```$", "", raw_text)

        # JSON変換して辞書形式で返却
        return json.loads(raw_text)

    except Exception as e:
        # パース失敗や通信エラー時のフォールバック処理
        return {
            "action_type": "GENERAL_CHAT",
            "target_date": None,
            "assistant_response": f"解析中にエラーが発生しました: {str(e)}",
            "meal_data": None,
            "exercise_data": None,
            "target_doc_id": None,
            "target_collection": None,
            "goal_data": None
        }
