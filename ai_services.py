import json
import streamlit as st
from google import genai
from google.genai import types
import firestore_db as db_module

# ---------------------------------------------------------
# Gemini API 初期化
# ---------------------------------------------------------
def get_gemini_client():
    """Google GenAI SDK クライアントの初期化"""
    try:
        api_key = st.secrets.get("GEMINI_API_KEY", None)
        if api_key:
            return genai.Client(api_key=api_key)
        return genai.Client()
    except Exception as e:
        st.error(f"⚠️ Gemini API初期化エラー: GEMINI_API_KEY を確認してください。({e})")
        return None

ai_client = get_gemini_client()

# ---------------------------------------------------------
# AI解析ロジック (Gemini 3.6 Flash)
# ---------------------------------------------------------
def generate_journal_feedback(note):
    if not ai_client or not note.strip():
        return ""
    prompt = f"""
あなたは親切で温かいパーソナルボディメイク＆メンタルコーチです。
ユーザーの本日のジャーナル（振り返り・メモ）に対して、150文字程度でポジティブなフィードバックやアドバイスを提供してください。

ユーザーの振り返り:
{note}
"""
    try:
        response = ai_client.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt
        )
        return response.text
    except Exception as e:
        return f"フィードバックの生成に失敗しました: {e}"

def parse_and_save_meal(user_text, target_date_str, is_eating_out=False, restaurant_name="", dining_partners="", eating_out_comment=""):
    if not ai_client:
        return "AIクライアントが初期化されていません。GEMINI_API_KEYを確認してください。"

    rules = db_module.fetch_user_rules()
    rules_text = ""
    if rules:
        rules_text = "\n【ユーザー指定の辞書登録・優先計算ルール】\n" + "\n".join([f"- {r.get('title')}: {r.get('detail')}" for r in rules]) + "\n※上記の辞書登録にある単語が含まれている場合は、その定義（例: 黄身なし、専用レシピの栄養素等）を最優先してカロリー・PFCを計算してください。\n"

    prompt = f"""
あなたは優しく優秀なパーソナルボディメイクコーチです。
ユーザーの発言から「食事」に関するデータを抽出し、以下のJSON形式厳守で出力してください。
{rules_text}
対象日付: {target_date_str}

【抽出フォーマット】
{{
  "meals": [
    {{
      "meal_type": "朝食", // 発言内容や入力時間帯から「朝食」「昼食」「夕食」「間食」のいずれかを推測。特定できない場合は「不明」としてください
      "food_name": "品目名", 
      "calories": 数値, 
      "protein": 数値, 
      "fat": 数値, 
      "carbs": 数値, 
      "alcohol_g": 数値
    }}
  ],
  "advice": "ユーザーへの温かい励ましと栄養アドバイス（100文字程度）"
}}

※食事データの該当がない場合は空配列 `[]` としてください。
※数値は推定でかまいません。

ユーザーの発言:
{user_text}
"""
    try:
        response = ai_client.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        data = json.loads(response.text)
        
        for m in data.get("meals", []):
            m["date"] = target_date_str
            m["is_eating_out"] = is_eating_out
            m["restaurant_name"] = restaurant_name if is_eating_out else ""
            m["dining_partners"] = dining_partners if is_eating_out else ""
            m["eating_out_comment"] = eating_out_comment if is_eating_out else ""
            db_module.save_meal_record(m)
                
        return data.get("advice", "食事記録を保存しました！")
    except Exception as e:
        return f"解析エラーが発生しました: {e}"

def parse_and_save_exercise(user_text, target_date_str):
    if not ai_client:
        return "AIクライアントが初期化されていません。"

    prompt = f"""
ユーザーの発言から「運動」に関するデータを抽出し、以下のJSON形式厳守で出力してください。

【抽出フォーマット】
{{
  "exercises": [
    {{"exercise_name": "種目名", "duration_min": 分数数値, "burned_calories": 数値}}
  ],
  "advice": "運動に対する短い労いのコメント（50文字程度）"
}}

ユーザーの発言:
{user_text}
"""
    try:
        response = ai_client.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        data = json.loads(response.text)
        
        for e in data.get("exercises", []):
            e["date"] = target_date_str
            db_module.save_exercise_record(e)
                
        return data.get("advice", "運動記録を保存しました！")
    except Exception as e:
        return f"解析エラーが発生しました: {e}"