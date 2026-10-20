import "server-only";
import { FieldValue, type DocumentSnapshot, type Timestamp } from "firebase-admin/firestore";
import { englishAudioBucket, firestore } from "../firebase";
import { isMock } from "../env";
import type { ReadText, Speech, SpeechJob, StudyLog } from "./types";

/**
 * 英語アプリのデータ操作。
 * コレクション名・フィールド名は Streamlit 版（english_db.py）と同じ（snake_case）。新旧どちらのアプリからも同じデータを読み書きできる。
 */
export interface EnglishStore {
  // 勉強ログ (english_study_logs)
  listStudyLogs(date: string): Promise<StudyLog[]>;
  listAllStudyLogs(): Promise<StudyLog[]>;
  addStudyLog(log: Omit<StudyLog, "id">): Promise<void>;
  updateStudyLog(id: string, log: Omit<StudyLog, "id" | "date">): Promise<void>;
  deleteStudyLog(id: string): Promise<void>;
  // 1分スピーチ (english_speeches) ※日付昇順
  listSpeeches(): Promise<Speech[]>;
  getSpeech(id: string): Promise<Speech | null>;
  addSpeech(speech: Omit<Speech, "id">): Promise<string>;
  deleteSpeech(id: string): Promise<void>;
  // 音声ファイル (Cloud Storage)
  uploadAudio(path: string, data: Buffer, contentType: string): Promise<void>;
  downloadAudio(path: string): Promise<Buffer>;
  deleteAudio(path: string): Promise<void>;
  // 読み上げ用の英文 (english_read_texts) ※新しい順
  listReadTexts(): Promise<ReadText[]>;
  addReadText(title: string, text: string): Promise<void>;
  updateReadText(id: string, title: string, text: string): Promise<void>;
  deleteReadText(id: string): Promise<void>;
  // スピーチ分析ジョブ (english_speech_jobs)
  createJob(date: string): Promise<SpeechJob>;
  updateJob(id: string, patch: Partial<Omit<SpeechJob, "id">>): Promise<void>;
  getJob(id: string): Promise<SpeechJob | null>;
  /** 実行中で開始から10分以内の最新ジョブ（画面を開き直したときに進み具合を表示するため） */
  findRunningJob(): Promise<SpeechJob | null>;
}

const JOB_TIMEOUT_MS = 10 * 60 * 1000;

const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : Number(v) || 0);
const str = (v: unknown) => (typeof v === "string" ? v : "");
const iso = (v: unknown) => {
  const t = v as Timestamp | undefined;
  return t && typeof t.toDate === "function" ? t.toDate().toISOString() : "";
};

function toStudyLog(d: DocumentSnapshot): StudyLog {
  const x = d.data() || {};
  return { id: d.id, date: str(x.date), minutes: num(x.minutes), skill: str(x.skill), content: str(x.content) };
}

function toSpeech(d: DocumentSnapshot): Speech {
  const x = d.data() || {};
  return {
    id: d.id,
    date: str(x.date),
    audioPath: str(x.audio_path),
    audioContentType: str(x.audio_content_type) || "audio/mp4",
    originalFilename: str(x.original_filename),
    transcript: str(x.transcript),
    naturalVersion: str(x.natural_version),
    suggestions: Array.isArray(x.suggestions)
      ? x.suggestions.map((s: Record<string, unknown>) => ({
          original: str(s?.original),
          better: str(s?.better),
          reason: str(s?.reason),
        }))
      : [],
    scores: (x.scores && typeof x.scores === "object" ? x.scores : {}) as Speech["scores"],
    overallComment: str(x.overall_comment),
    growthComment: str(x.growth_comment),
  };
}

function toReadText(d: DocumentSnapshot): ReadText {
  const x = d.data() || {};
  return { id: d.id, title: str(x.title), text: str(x.text), createdAt: iso(x.created_at) };
}

function toJob(d: DocumentSnapshot): SpeechJob {
  const x = d.data() || {};
  return {
    id: d.id,
    status: (x.status as SpeechJob["status"]) || "error",
    date: str(x.date),
    startedAt: iso(x.started_at),
    speechId: x.speech_id ? str(x.speech_id) : undefined,
    error: x.error ? str(x.error) : undefined,
  };
}

const firestoreStore: EnglishStore = {
  async listStudyLogs(date) {
    const snap = await firestore().collection("english_study_logs").where("date", "==", date).get();
    return snap.docs.map(toStudyLog);
  },
  async listAllStudyLogs() {
    const snap = await firestore().collection("english_study_logs").get();
    return snap.docs.map(toStudyLog);
  },
  async addStudyLog(log) {
    await firestore().collection("english_study_logs").add({
      date: log.date,
      minutes: log.minutes,
      skill: log.skill,
      content: log.content,
      created_at: FieldValue.serverTimestamp(),
    });
  },
  async updateStudyLog(id, log) {
    await firestore().collection("english_study_logs").doc(id).update({
      minutes: log.minutes,
      skill: log.skill,
      content: log.content,
    });
  },
  async deleteStudyLog(id) {
    await firestore().collection("english_study_logs").doc(id).delete();
  },

  async listSpeeches() {
    const snap = await firestore().collection("english_speeches").get();
    return snap.docs.map(toSpeech).sort((a, b) => a.date.localeCompare(b.date));
  },
  async getSpeech(id) {
    const d = await firestore().collection("english_speeches").doc(id).get();
    return d.exists ? toSpeech(d) : null;
  },
  async addSpeech(s) {
    const ref = await firestore().collection("english_speeches").add({
      date: s.date,
      audio_path: s.audioPath,
      audio_content_type: s.audioContentType,
      original_filename: s.originalFilename,
      transcript: s.transcript,
      natural_version: s.naturalVersion,
      suggestions: s.suggestions,
      scores: s.scores,
      overall_comment: s.overallComment,
      growth_comment: s.growthComment,
      created_at: FieldValue.serverTimestamp(),
    });
    return ref.id;
  },
  async deleteSpeech(id) {
    await firestore().collection("english_speeches").doc(id).delete();
  },

  async uploadAudio(path, data, contentType) {
    await englishAudioBucket().file(path).save(data, { contentType, resumable: false });
  },
  async downloadAudio(path) {
    const [buf] = await englishAudioBucket().file(path).download();
    return buf;
  },
  async deleteAudio(path) {
    await englishAudioBucket().file(path).delete({ ignoreNotFound: true });
  },

  async listReadTexts() {
    const snap = await firestore().collection("english_read_texts").get();
    return snap.docs.map(toReadText).sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  },
  async addReadText(title, text) {
    await firestore().collection("english_read_texts").add({
      title,
      text,
      created_at: FieldValue.serverTimestamp(),
      updated_at: FieldValue.serverTimestamp(),
    });
  },
  async updateReadText(id, title, text) {
    await firestore().collection("english_read_texts").doc(id).update({
      title,
      text,
      updated_at: FieldValue.serverTimestamp(),
    });
  },
  async deleteReadText(id) {
    await firestore().collection("english_read_texts").doc(id).delete();
  },

  async createJob(date) {
    const ref = await firestore().collection("english_speech_jobs").add({
      status: "running",
      date,
      started_at: FieldValue.serverTimestamp(),
    });
    return { id: ref.id, status: "running", date, startedAt: new Date().toISOString() };
  },
  async updateJob(id, patch) {
    const data: Record<string, unknown> = {};
    if (patch.status) data.status = patch.status;
    if (patch.speechId) data.speech_id = patch.speechId;
    if (patch.error) data.error = patch.error;
    await firestore().collection("english_speech_jobs").doc(id).update(data);
  },
  async getJob(id) {
    const d = await firestore().collection("english_speech_jobs").doc(id).get();
    return d.exists ? toJob(d) : null;
  },
  async findRunningJob() {
    const snap = await firestore().collection("english_speech_jobs").where("status", "==", "running").get();
    const jobs = snap.docs
      .map(toJob)
      .filter((j) => j.startedAt && Date.now() - new Date(j.startedAt).getTime() < JOB_TIMEOUT_MS)
      .sort((a, b) => b.startedAt.localeCompare(a.startedAt));
    return jobs[0] || null;
  },
};

// ---------------------------------------------------------------------------
// ローカル開発用のメモリ上のダミーデータ（MOCK_BACKEND=1 のときのみ）
// ---------------------------------------------------------------------------
type Mem = {
  logs: StudyLog[];
  speeches: Speech[];
  texts: ReadText[];
  jobs: SpeechJob[];
  audio: Map<string, { data: Buffer; contentType: string }>;
  seq: number;
};

function seedMemory(): Mem {
  const skills = ["リスニング", "スピーキング", "リーディング", "ライティング", "語彙", "文法", "発音"];
  const today = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Tokyo" }).format(new Date());
  const day = (offset: number) => {
    const d = new Date(today + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() - offset);
    return d.toISOString().slice(0, 10);
  };
  const logs: StudyLog[] = [];
  for (let i = 0; i < 80; i++) {
    if ((i * 7) % 10 < 3) continue;
    logs.push({ id: `l${i}`, date: day(i), minutes: [15, 30, 45, 60][i % 4], skill: skills[(i * 3) % 7], content: "Podcast" });
  }
  const speeches: Speech[] = [5, 4, 3, 2, 1].map((w, i) => ({
    id: `s${i}`,
    date: day(w * 7 + 1),
    audioPath: "",
    audioContentType: "audio/mp4",
    originalFilename: "",
    transcript: "Last weekend, uh, I go to the park with my family.",
    naturalVersion: "Last weekend, I went to the park with my family. We had a picnic and played catch.",
    suggestions: [{ original: "I go to the park", better: "I went to the park", reason: "過去の出来事なので過去形にします。" }],
    scores: { total: 50 + i * 2, grammar: 48 + i, vocabulary: 52, fluency: 45 + i * 2, content: 55, pronunciation: 50 },
    overallComment: "内容はよく伝わっています。過去形を意識しましょう。",
    growthComment: i === 4 ? "流暢さが少しずつ向上しています。" : "",
  }));
  const texts: ReadText[] = [
    { id: "t0", title: "週末", text: "Last weekend, I went hiking with my family. It was great!", createdAt: "2026-01-01T00:00:00.000Z" },
  ];
  return { logs, speeches, texts, jobs: [], audio: new Map(), seq: 100 };
}

const g = globalThis as unknown as { __englishMem?: Mem };
const mem = () => (g.__englishMem ??= seedMemory());
const nextId = (p: string) => `${p}${mem().seq++}`;

const memoryStore: EnglishStore = {
  async listStudyLogs(date) {
    return mem().logs.filter((l) => l.date === date);
  },
  async listAllStudyLogs() {
    return [...mem().logs];
  },
  async addStudyLog(log) {
    mem().logs.push({ ...log, id: nextId("l") });
  },
  async updateStudyLog(id, log) {
    const l = mem().logs.find((x) => x.id === id);
    if (l) Object.assign(l, log);
  },
  async deleteStudyLog(id) {
    mem().logs = mem().logs.filter((x) => x.id !== id);
  },
  async listSpeeches() {
    return [...mem().speeches].sort((a, b) => a.date.localeCompare(b.date));
  },
  async getSpeech(id) {
    return mem().speeches.find((s) => s.id === id) || null;
  },
  async addSpeech(s) {
    const id = nextId("s");
    mem().speeches.push({ ...s, id });
    return id;
  },
  async deleteSpeech(id) {
    mem().speeches = mem().speeches.filter((s) => s.id !== id);
  },
  async uploadAudio(path, data, contentType) {
    mem().audio.set(path, { data, contentType });
  },
  async downloadAudio(path) {
    const a = mem().audio.get(path);
    if (!a) throw new Error("not found");
    return a.data;
  },
  async deleteAudio(path) {
    mem().audio.delete(path);
  },
  async listReadTexts() {
    return [...mem().texts].sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  },
  async addReadText(title, text) {
    mem().texts.push({ id: nextId("t"), title, text, createdAt: new Date().toISOString() });
  },
  async updateReadText(id, title, text) {
    const t = mem().texts.find((x) => x.id === id);
    if (t) Object.assign(t, { title, text });
  },
  async deleteReadText(id) {
    mem().texts = mem().texts.filter((x) => x.id !== id);
  },
  async createJob(date) {
    const job: SpeechJob = { id: nextId("j"), status: "running", date, startedAt: new Date().toISOString() };
    mem().jobs.push(job);
    return { ...job };
  },
  async updateJob(id, patch) {
    const j = mem().jobs.find((x) => x.id === id);
    if (j) Object.assign(j, patch);
  },
  async getJob(id) {
    const j = mem().jobs.find((x) => x.id === id);
    return j ? { ...j } : null;
  },
  async findRunningJob() {
    const running = mem()
      .jobs.filter((j) => j.status === "running" && Date.now() - new Date(j.startedAt).getTime() < JOB_TIMEOUT_MS)
      .sort((a, b) => b.startedAt.localeCompare(a.startedAt));
    return running[0] ? { ...running[0] } : null;
  },
};

export function englishStore(): EnglishStore {
  return isMock ? memoryStore : firestoreStore;
}
