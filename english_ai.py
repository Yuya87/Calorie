import json
import os
import subprocess
import tempfile
import streamlit as st
from google.genai import types
import imageio_ffmpeg

# Gemini クライアント・モデルは Body Make アプリと共通のものを流用する
from ai_services import ai_client, MODEL_NAME

# ---------------------------------------------------------
# 音声変換（ボイスメモ m4a 等 → Gemini が確実に扱える WAV 16kHz モノラル）
# ---------------------------------------------------------
def convert_to_wav(audio_bytes, ext):
    """音声を WAV (16kHz / mono) に変換して返す。失敗時は None"""
    src_path = dst_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as src:
            src.write(audio_bytes)
            src_path = src.name
        dst_path = src_path + ".wav"
        subprocess.run(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
             "-i", src_path, "-ac", "1", "-ar", "16000", dst_path],
            check=True, capture_output=True, timeout=120
        )
        with open(dst_path, "rb") as f:
            return f.read()
    except Exception as e:
        st.error(f"音声の変換に失敗しました: {e}")
        return None
    finally:
        for p in (src_path, dst_path):
            if p and os.path.exists(p):
                os.remove(p)

# ---------------------------------------------------------
# 1分スピーチ分析
# ---------------------------------------------------------
SCORE_KEYS = ["total", "grammar", "vocabulary", "fluency", "content", "pronunciation"]

# 点数の基準（CEFR に対応づけて、回ごとの採点のブレを抑える）
SCORING_RUBRIC = """
各項目 0〜100点。以下の基準で採点すること（CEFRの目安）:
- 95〜100: 教養ある英語ネイティブと同等。誤りがほぼなく、自然で洗練されている (C2上位)
- 85〜94: 非常に流暢で正確。ネイティブにも違和感がほとんどない (C2)
- 70〜84: 複雑な内容も流暢に話せる。時々不自然な表現がある (C1)
- 55〜69: 日常的な話題なら問題なく伝えられる。誤りはあるが意味は通じる (B2)
- 40〜54: 身近な話題を簡単な表現でつなげて話せる。誤りや言いよどみが目立つ (B1)
- 25〜39: 短い簡単な文で基本的な内容を伝えられる (A2)
- 0〜24: 単語や定型句が中心 (A1)
total は各項目を踏まえた総合評価（単純平均である必要はない）。甘くせず、同じ基準で一貫して採点すること。
"""

def _format_past_speeches(past_speeches):
    lines = []
    for s in past_speeches:
        scores = s.get("scores", {}) or {}
        score_text = ", ".join(f"{k}={scores.get(k)}" for k in SCORE_KEYS if k in scores)
        lines.append(f"- {s.get('date')}: [{score_text}]\n  文字起こし: {s.get('transcript', '')}")
    return "\n".join(lines) if lines else "（過去のスピーチなし）"

def analyze_speech(wav_bytes, past_speeches=None):
    """1分スピーチの音声を分析し、結果dictを返す。失敗時は None

    past_speeches: 比較用の過去スピーチ（date / transcript / scores を持つdictのリスト）
    """
    if not ai_client:
        st.error("⚠️ Gemini API が利用できません。GEMINI_API_KEY を確認してください。")
        return None
    if not wav_bytes:
        return None

    prompt = f"""
あなたは経験豊富な英語スピーキングコーチです。
添付の音声は、日本人の英語学習者による約1分間の英語スピーチ（主に週末の出来事について）です。
音声を聞いて、以下を日本語で（英文部分は英語で）JSON形式で返してください。

1. transcript: 話した内容の正確な文字起こし（言いよどみ "uh", "um" や言い直しもそのまま残す）
2. natural_version: 話した内容を、意味を変えずに自然な英語に直したスピーチ全文
3. suggestions: より自然な言い回しの提案（重要なものから最大6件）。各要素は
   {{"original": 話した表現, "better": より自然な表現, "reason": 理由（日本語・1文）}}
4. scores: {{"total", "grammar", "vocabulary", "fluency", "content", "pronunciation"}} の各点数（整数）
   - grammar: 文法の正確さ / vocabulary: 語彙の幅と適切さ / fluency: 流暢さ（間・言いよどみ・速さ）
   - content: 内容の伝わりやすさ（構成・具体性） / pronunciation: 発音・イントネーション（音声から判断）
5. overall_comment: 総評と次回に向けた具体的なアドバイス（日本語・3文程度）
6. growth_comment: 下の「過去のスピーチ」と比べて、特筆すべき変化（明確な成長や後退）があれば日本語で2〜3文。
   特筆すべき変化がない場合や過去のスピーチがない場合は空文字 "" にすること。

【採点基準】
{SCORING_RUBRIC}

【過去のスピーチ（比較用）】
{_format_past_speeches(past_speeches or [])}

出力JSON形式:
{{
  "transcript": "...",
  "natural_version": "...",
  "suggestions": [{{"original": "...", "better": "...", "reason": "..."}}],
  "scores": {{"total": 0, "grammar": 0, "vocabulary": 0, "fluency": 0, "content": 0, "pronunciation": 0}},
  "overall_comment": "...",
  "growth_comment": ""
}}
"""
    try:
        response = ai_client.models.generate_content(
            model=MODEL_NAME,
            contents=[types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"), prompt],
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        result = json.loads(response.text)
        scores = result.get("scores", {}) or {}
        result["scores"] = {k: int(round(float(scores.get(k, 0) or 0))) for k in SCORE_KEYS}
        result["suggestions"] = result.get("suggestions") or []
        result["growth_comment"] = (result.get("growth_comment") or "").strip()
        return result
    except Exception as e:
        st.error(f"スピーチの分析に失敗しました: {e}")
        return None
