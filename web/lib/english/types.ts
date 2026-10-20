import type { ScoreKey } from "./constants";

export type StudyLog = {
  id: string;
  date: string;
  minutes: number;
  skill: string;
  content: string;
};

export type Suggestion = { original: string; better: string; reason: string };

export type Speech = {
  id: string;
  date: string;
  audioPath: string;
  audioContentType: string;
  originalFilename: string;
  transcript: string;
  naturalVersion: string;
  suggestions: Suggestion[];
  scores: Partial<Record<ScoreKey, number>>;
  overallComment: string;
  growthComment: string;
};

export type ReadText = {
  id: string;
  title: string;
  text: string;
  createdAt: string;
};

export type SpeechJobStatus = "running" | "done" | "error";

/** スピーチ分析ジョブ（分析は1分ほどかかるため、画面とは切り離して実行し状態を保存する） */
export type SpeechJob = {
  id: string;
  status: SpeechJobStatus;
  date: string;
  startedAt: string;
  speechId?: string;
  error?: string;
};

export type SpeechAnalysis = {
  transcript: string;
  naturalVersion: string;
  suggestions: Suggestion[];
  scores: Record<ScoreKey, number>;
  overallComment: string;
  growthComment: string;
};
