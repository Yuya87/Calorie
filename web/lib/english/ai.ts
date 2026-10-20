import "server-only";
import { GoogleGenAI } from "@google/genai";
import { isMock } from "../env";
import { SCORE_KEYS, type ScoreKey } from "./constants";
import type { Speech, SpeechAnalysis } from "./types";

/** 点数の基準（CEFR に対応づけて、回ごとの採点のブレを抑える）。Streamlit 版と同じ */
const SCORING_RUBRIC = `
各項目 0〜100点。以下の基準で採点すること（CEFRの目安）:
- 95〜100: 教養ある英語ネイティブと同等。誤りがほぼなく、自然で洗練されている (C2上位)
- 85〜94: 非常に流暢で正確。ネイティブにも違和感がほとんどない (C2)
- 70〜84: 複雑な内容も流暢に話せる。時々不自然な表現がある (C1)
- 55〜69: 日常的な話題なら問題なく伝えられる。誤りはあるが意味は通じる (B2)
- 40〜54: 身近な話題を簡単な表現でつなげて話せる。誤りや言いよどみが目立つ (B1)
- 25〜39: 短い簡単な文で基本的な内容を伝えられる (A2)
- 0〜24: 単語や定型句が中心 (A1)
total は各項目を踏まえた総合評価（単純平均である必要はない）。甘くせず、同じ基準で一貫して採点すること。
`;

function formatPastSpeeches(past: Speech[]): string {
  if (!past.length) return "（過去のスピーチなし）";
  return past
    .map((s) => {
      const scoreText = SCORE_KEYS.filter((k) => s.scores[k] !== undefined)
        .map((k) => `${k}=${s.scores[k]}`)
        .join(", ");
      return `- ${s.date}: [${scoreText}]\n  文字起こし: ${s.transcript}`;
    })
    .join("\n");
}

function buildPrompt(past: Speech[]): string {
  return `
あなたは経験豊富な英語スピーキングコーチです。
添付の音声は、日本人の英語学習者による約1分間の英語スピーチ（主に週末の出来事について）です。
音声を聞いて、以下を日本語で（英文部分は英語で）JSON形式で返してください。

1. transcript: 話した内容の正確な文字起こし（言いよどみ "uh", "um" や言い直しもそのまま残す）
2. natural_version: 話した内容を、意味を変えずに自然な英語に直したスピーチ全文
3. suggestions: より自然な言い回しの提案（重要なものから最大6件）。各要素は
   {"original": 話した表現, "better": より自然な表現, "reason": 理由（日本語・1文）}
4. scores: {"total", "grammar", "vocabulary", "fluency", "content", "pronunciation"} の各点数（整数）
   - grammar: 文法の正確さ / vocabulary: 語彙の幅と適切さ / fluency: 流暢さ（間・言いよどみ・速さ）
   - content: 内容の伝わりやすさ（構成・具体性） / pronunciation: 発音・イントネーション（音声から判断）
5. overall_comment: 総評と次回に向けた具体的なアドバイス（日本語・3文程度）
6. growth_comment: 下の「過去のスピーチ」と比べて、特筆すべき変化（明確な成長や後退）があれば日本語で2〜3文。
   特筆すべき変化がない場合や過去のスピーチがない場合は空文字 "" にすること。

【採点基準】
${SCORING_RUBRIC}

【過去のスピーチ（比較用）】
${formatPastSpeeches(past)}

出力JSON形式:
{
  "transcript": "...",
  "natural_version": "...",
  "suggestions": [{"original": "...", "better": "...", "reason": "..."}],
  "scores": {"total": 0, "grammar": 0, "vocabulary": 0, "fluency": 0, "content": 0, "pronunciation": 0},
  "overall_comment": "...",
  "growth_comment": ""
}
`;
}

function normalize(raw: Record<string, unknown>): SpeechAnalysis {
  const rawScores = (raw.scores || {}) as Record<string, unknown>;
  const scores = Object.fromEntries(
    SCORE_KEYS.map((k) => [k, Math.round(Number(rawScores[k]) || 0)]),
  ) as Record<ScoreKey, number>;
  const suggestions = Array.isArray(raw.suggestions)
    ? (raw.suggestions as Record<string, unknown>[]).map((s) => ({
        original: String(s?.original ?? ""),
        better: String(s?.better ?? ""),
        reason: String(s?.reason ?? ""),
      }))
    : [];
  return {
    transcript: String(raw.transcript ?? ""),
    naturalVersion: String(raw.natural_version ?? ""),
    suggestions,
    scores,
    overallComment: String(raw.overall_comment ?? ""),
    growthComment: String(raw.growth_comment ?? "").trim(),
  };
}

/** 1分スピーチ（WAV 16kHz モノラル）を分析する。失敗時は例外 */
export async function analyzeSpeech(wav: Buffer, past: Speech[]): Promise<SpeechAnalysis> {
  if (isMock) {
    await new Promise((r) => setTimeout(r, 4000));
    return normalize({
      transcript: "I went hiking, uh, on Saturday with my friends.",
      natural_version: "I went hiking with my friends on Saturday. The weather was perfect.",
      suggestions: [{ original: "I go hiking", better: "I went hiking", reason: "過去形にします。" }],
      scores: { total: 62, grammar: 60, vocabulary: 58, fluency: 55, content: 70, pronunciation: 61 },
      overall_comment: "（ダミー）構成がわかりやすいです。",
      growth_comment: "",
    });
  }
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) throw new Error("GEMINI_API_KEY が設定されていません。");
  const ai = new GoogleGenAI({ apiKey });
  try {
    const res = await ai.models.generateContent({
      model: process.env.GEMINI_MODEL || "gemini-3.6-flash",
      contents: [
        {
          role: "user",
          parts: [{ inlineData: { mimeType: "audio/wav", data: wav.toString("base64") } }, { text: buildPrompt(past) }],
        },
      ],
      config: { responseMimeType: "application/json" },
    });
    return normalize(JSON.parse(res.text || "{}"));
  } catch (e) {
    throw new Error(`スピーチの分析に失敗しました: ${e instanceof Error ? e.message : String(e)}`);
  }
}

/** 比較用の過去スピーチ: 直近4回＋約3か月前に最も近い1回（Streamlit 版と同じ） */
export function pickPastSpeeches(speeches: Speech[], date: string): Speech[] {
  const past = speeches.filter((s) => s.date < date);
  const recent = past.slice(-4);
  const older = past.slice(0, Math.max(0, past.length - 4));
  if (!older.length) return recent;
  const target = new Date(date + "T00:00:00Z").getTime() - 90 * 86400000;
  const closest = older.reduce((best, s) =>
    Math.abs(new Date(s.date + "T00:00:00Z").getTime() - target) <
    Math.abs(new Date(best.date + "T00:00:00Z").getTime() - target)
      ? s
      : best,
  );
  return [closest, ...recent];
}
