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
MODEL_NAME = 'gemini-3.6-flash'

def _generate_json(prompt):
    """JSONレスポンスモードで生成し、dictとして返す"""
    response = ai_client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        )
    )
    return json.loads(response.text)

def _format_meals(meals):
    """食事ログをプロンプト用の箇条書きに整形（日付→食事種別順）"""
    order = {"朝食": 0, "昼食": 1, "夕食": 2, "間食": 3, "不明": 4}
    meals = sorted(meals, key=lambda m: (m.get("date", ""), order.get(m.get("meal_type"), 9)))
    lines = []
    for m in meals:
        line = (f"- {m.get('date')} {m.get('meal_type', '不明')}: {m.get('food_name', '')} "
                f"({float(m.get('calories', 0)):.0f}kcal, P{float(m.get('protein', 0)):.0f}g "
                f"F{float(m.get('fat', 0)):.0f}g C{float(m.get('carbs', 0)):.0f}g")
        if float(m.get("alcohol_g", 0) or 0) > 0:
            line += f", アルコール{float(m.get('alcohol_g', 0)):.0f}g"
        line += ")"
        if m.get("is_eating_out"):
            line += f" [外食: {m.get('restaurant_name', '')}]"
        lines.append(line)
    return "\n".join(lines) if lines else "（記録なし）"

def analyze_meal_text(meal_text, dict_rules=None):
    """食事テキストを解析し、1件分の栄養素dictを返す。失敗時は None"""
    if not ai_client or not meal_text.strip():
        return None

    rules_text = ""
    if dict_rules:
        rules_text = "\n【ユーザー指定の辞書登録・優先計算ルール】\n" + "\n".join([f"- {r.get('title')}: {r.get('detail')}" for r in dict_rules]) + "\n※上記の辞書登録にある単語が含まれている場合は、その定義を最優先してカロリー・PFCを計算してください。\n"

    prompt = f"""
あなたは優秀な管理栄養士です。
ユーザーが入力した1回分の食事内容から、合計のカロリー・PFC・アルコール量を推定し、以下のJSON形式厳守で出力してください。
{rules_text}
【出力フォーマット】
{{
  "food_name": "品目名（複数ある場合は「ラーメン、餃子、ビール」のように読点区切り）",
  "calories": 数値,
  "protein": 数値,
  "fat": 数値,
  "carbs": 数値,
  "alcohol_g": 数値
}}

※数値は推定でかまいません。単位は kcal / g です。

ユーザーの入力:
{meal_text}
"""
    try:
        return _generate_json(prompt)
    except Exception as e:
        st.error(f"食事の解析に失敗しました: {e}")
        return None

def analyze_exercise_text(exercise_text):
    """運動テキストを解析し、1件分の運動dictを返す。失敗時は None"""
    if not ai_client or not exercise_text.strip():
        return None

    prompt = f"""
ユーザーが入力した運動内容から、種目名・合計時間・合計消費カロリーを推定し、以下のJSON形式厳守で出力してください。

【出力フォーマット】
{{
  "exercise_name": "種目名（複数ある場合は読点区切り）",
  "duration_min": 分数の数値,
  "burned_calories": 数値
}}

ユーザーの入力:
{exercise_text}
"""
    try:
        return _generate_json(prompt)
    except Exception as e:
        st.error(f"運動の解析に失敗しました: {e}")
        return None

def generate_meal_feedback(date_str, new_meal, recent_meals, goals):
    """食事登録直後のウィットに富んだフィードバックコメントを生成"""
    if not ai_client:
        return ""

    today_meals = [m for m in recent_meals if m.get("date") == date_str]
    past_meals = [m for m in recent_meals if m.get("date") != date_str]
    today_cal = sum(float(m.get("calories", 0) or 0) for m in today_meals)
    today_p = sum(float(m.get("protein", 0) or 0) for m in today_meals)

    prompt = f"""
あなたはユーモアのセンス抜群で、ちょっと皮肉も言えるけれど根は温かいパーソナルボディメイクコーチです。
ユーザーが今登録した食事について、当日と直近3日間の食事の流れを踏まえたフィードバックを書いてください。

【ルール】
- 120〜180文字程度、絵文字は1〜2個まで
- ウィットに富んだ一言（たとえ・ツッコミ・軽いダジャレなど）を必ず1つ入れる
- 直近の食事との関係（連日の同じメニュー、PFCの偏り、飲酒の続き具合、良い流れなど）に具体的に触れる
- 説教臭くせず、次も記録したくなるように前向きに締める
- 良い点は素直に褒め、改善点は1つだけ具体的に提案する

【今登録した食事】
{_format_meals([new_meal])}

【当日の食事（今回分を含む）】
{_format_meals(today_meals)}
当日合計: {today_cal:.0f}kcal / 目標 {float(goals.get('target_cal', 0)):.0f}kcal、タンパク質 {today_p:.0f}g / 目標 {float(goals.get('target_p', 0)):.0f}g

【直近3日間の食事】
{_format_meals(past_meals)}

【出力フォーマット】
{{"feedback": "フィードバック本文"}}
"""
    try:
        return _generate_json(prompt).get("feedback", "")
    except Exception as e:
        return f"フィードバックの生成に失敗しました: {e}"

def generate_journal_feedback(date_str, journal_note, habit_data=None, meals_data=None, exercises_data=None):
    """ジャーナル＋当日の習慣・食事・運動を踏まえたフィードバックを生成"""
    if not ai_client or not journal_note.strip():
        return ""

    habit_data = habit_data or {}
    exercises_text = "\n".join(
        f"- {e.get('exercise_name', '')} {float(e.get('duration_min', 0) or 0):.0f}分 "
        f"({float(e.get('burned_calories', 0) or 0):.0f}kcal)"
        for e in (exercises_data or [])
    ) or "（記録なし）"

    prompt = f"""
あなたは親切で温かいパーソナルボディメイク＆メンタルコーチです。
ユーザーの本日（{date_str}）のジャーナルと記録データを踏まえて、150文字程度でポジティブなフィードバックやアドバイスを提供してください。

【習慣チェックイン】
運動: {habit_data.get('gym', '未記録')} / 英語学習: {habit_data.get('english', '未記録')} / 休肝日: {'飲酒' if habit_data.get('rest_day') == '未実施' else habit_data.get('rest_day', '未記録')}

【本日の食事】
{_format_meals(meals_data or [])}

【本日の運動】
{exercises_text}

【ユーザーの振り返り】
{journal_note}
"""
    try:
        response = ai_client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt
        )
        return response.text
    except Exception as e:
        return f"フィードバックの生成に失敗しました: {e}"
