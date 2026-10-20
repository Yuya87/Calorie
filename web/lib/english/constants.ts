/** 学習の目的に応じて1つだけ選ぶ技能（技能別の合計が総勉強時間と一致するよう単一選択） */
export const SKILLS = ["リスニング", "スピーキング", "リーディング", "ライティング", "語彙", "文法", "発音"] as const;
export type Skill = (typeof SKILLS)[number];

/** 技能ごとの固定色（検証済みカテゴリ配色。並び順＝割り当て順で固定。Streamlit 版と同じ） */
export const SKILL_COLORS: Record<string, string> = {
  リスニング: "#2a78d6",
  スピーキング: "#eb6834",
  リーディング: "#1baf7a",
  ライティング: "#eda100",
  語彙: "#e87ba4",
  文法: "#008300",
  発音: "#4a3aa7",
};

export const SCORE_KEYS = ["total", "grammar", "vocabulary", "fluency", "content", "pronunciation"] as const;
export type ScoreKey = (typeof SCORE_KEYS)[number];

export const SCORE_LABELS: Record<ScoreKey, string> = {
  total: "総合",
  grammar: "文法",
  vocabulary: "語彙",
  fluency: "流暢さ",
  content: "内容の伝わりやすさ",
  pronunciation: "発音",
};

/** アップロード可能な音声（拡張子 → Content-Type） */
export const AUDIO_TYPES: Record<string, string> = {
  m4a: "audio/mp4",
  mp4: "audio/mp4",
  mp3: "audio/mpeg",
  wav: "audio/wav",
  aac: "audio/aac",
};

/** Vercel の関数が受け取れるリクエストの上限（4.5MB）に余裕を持たせた値 */
export const MAX_UPLOAD_BYTES = 4_300_000;
