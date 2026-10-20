"use server";

import { revalidatePath } from "next/cache";
import { isValidDate } from "../date";
import { requireUser } from "../session";
import { SKILLS } from "./constants";
import { englishStore } from "./store";

export type ActionResult = { ok: true } | { ok: false; error: string };

async function run(fn: () => Promise<void>): Promise<ActionResult> {
  try {
    await requireUser();
    await fn();
    revalidatePath("/english", "layout");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}

function validMinutes(m: number) {
  if (!Number.isFinite(m) || m < 1 || m > 600) throw new Error("勉強時間は1〜600分で入力してください。");
  return m;
}

function validSkill(s: string) {
  if (!(SKILLS as readonly string[]).includes(s)) throw new Error("技能を1つ選択してください。");
  return s;
}

// ---- 勉強ログ ----
export async function addStudyLog(input: { date: string; minutes: number; skill: string; content: string }) {
  return run(async () => {
    if (!isValidDate(input.date)) throw new Error("日付が正しくありません。");
    await englishStore().addStudyLog({
      date: input.date,
      minutes: validMinutes(input.minutes),
      skill: validSkill(input.skill),
      content: input.content.trim(),
    });
  });
}

export async function updateStudyLog(id: string, input: { minutes: number; skill: string; content: string }) {
  return run(() =>
    englishStore().updateStudyLog(id, {
      minutes: validMinutes(input.minutes),
      skill: validSkill(input.skill),
      content: input.content.trim(),
    }),
  );
}

export async function deleteStudyLog(id: string) {
  return run(() => englishStore().deleteStudyLog(id));
}

// ---- スピーチ ----
export async function deleteSpeech(id: string) {
  return run(async () => {
    const store = englishStore();
    const speech = await store.getSpeech(id);
    await store.deleteSpeech(id);
    if (speech?.audioPath) await store.deleteAudio(speech.audioPath).catch(() => undefined);
  });
}

// ---- 読み上げ用の英文 ----
export async function addReadText(title: string, text: string) {
  return run(async () => {
    if (!text.trim()) throw new Error("英文を入力してください。");
    await englishStore().addReadText(title.trim(), text.trim());
  });
}

export async function updateReadText(id: string, title: string, text: string) {
  return run(async () => {
    if (!text.trim()) throw new Error("英文を入力してください。");
    await englishStore().updateReadText(id, title.trim(), text.trim());
  });
}

export async function deleteReadText(id: string) {
  return run(() => englishStore().deleteReadText(id));
}
