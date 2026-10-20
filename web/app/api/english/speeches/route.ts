import { after, NextResponse } from "next/server";
import { randomBytes } from "crypto";
import { isValidDate } from "@/lib/date";
import { requireUser } from "@/lib/session";
import { analyzeSpeech, pickPastSpeeches } from "@/lib/english/ai";
import { AUDIO_TYPES, MAX_UPLOAD_BYTES } from "@/lib/english/constants";
import { englishStore } from "@/lib/english/store";

// 分析（Gemini）は1分ほどかかることがあるため、関数の実行時間の上限を引き上げる
export const maxDuration = 60;

/**
 * スピーチ音声を受け取り、分析ジョブを開始してすぐにジョブIDを返す。
 * 分析・保存はレスポンス後に after() で続行するため、スマホの画面スリープ等で接続が切れても結果は保存される。
 * 画面は /api/english/jobs/[id] で進み具合を確認する。
 */
export async function POST(req: Request) {
  try {
    await requireUser();
  } catch {
    return NextResponse.json({ error: "ログインが必要です。" }, { status: 401 });
  }

  const form = await req.formData();
  const original = form.get("original");
  const wav = form.get("wav");
  const date = String(form.get("date") || "");
  if (!(original instanceof File) || !(wav instanceof File)) {
    return NextResponse.json({ error: "音声ファイルがありません。" }, { status: 400 });
  }
  if (!isValidDate(date)) return NextResponse.json({ error: "日付が正しくありません。" }, { status: 400 });
  if (original.size + wav.size > MAX_UPLOAD_BYTES) {
    return NextResponse.json({ error: "音声が長すぎます（目安: 2分以内）。" }, { status: 413 });
  }
  const ext = (original.name.split(".").pop() || "").toLowerCase();
  const contentType = AUDIO_TYPES[ext];
  if (!contentType) return NextResponse.json({ error: "対応していない音声形式です。" }, { status: 400 });

  const originalBuf = Buffer.from(await original.arrayBuffer());
  const wavBuf = Buffer.from(await wav.arrayBuffer());
  const store = englishStore();
  const job = await store.createJob(date);

  after(async () => {
    let audioPath = "";
    try {
      const past = pickPastSpeeches(await store.listSpeeches(), date);
      const result = await analyzeSpeech(wavBuf, past);
      audioPath = `english_speeches/${date}_${randomBytes(4).toString("hex")}.${ext}`;
      await store.uploadAudio(audioPath, originalBuf, contentType);
      const speechId = await store.addSpeech({
        date,
        audioPath,
        audioContentType: contentType,
        originalFilename: original.name,
        ...result,
      });
      await store.updateJob(job.id, { status: "done", speechId });
    } catch (e) {
      // 分析結果を保存できなかった場合は、アップロード済みの音声を残さない
      if (audioPath) await store.deleteAudio(audioPath).catch(() => undefined);
      await store
        .updateJob(job.id, { status: "error", error: e instanceof Error ? e.message : String(e) })
        .catch(() => undefined);
    }
  });

  return NextResponse.json({ jobId: job.id });
}
