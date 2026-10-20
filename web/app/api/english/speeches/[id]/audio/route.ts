import { NextResponse } from "next/server";
import { requireUser } from "@/lib/session";
import { englishStore } from "@/lib/english/store";

/** スピーチ音声の再生・ダウンロード（?download=1 でファイルとして保存） */
export async function GET(req: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    await requireUser();
  } catch {
    return NextResponse.json({ error: "ログインが必要です。" }, { status: 401 });
  }
  const { id } = await params;
  const store = englishStore();
  const speech = await store.getSpeech(id);
  if (!speech?.audioPath) return NextResponse.json({ error: "音声がありません。" }, { status: 404 });
  try {
    const data = await store.downloadAudio(speech.audioPath);
    const headers: Record<string, string> = {
      "Content-Type": speech.audioContentType,
      "Accept-Ranges": "bytes",
      "Cache-Control": "private, max-age=86400",
    };
    if (new URL(req.url).searchParams.get("download")) {
      const name = speech.originalFilename || `speech_${speech.date}.m4a`;
      headers["Content-Disposition"] = `attachment; filename*=UTF-8''${encodeURIComponent(name)}`;
    }
    // iPhone の Safari は音声再生時に部分取得（Range）を要求し、対応していないと再生できないため 206 で返す
    const range = /^bytes=(\d*)-(\d*)$/.exec(req.headers.get("range") || "");
    if (range && (range[1] || range[2])) {
      const size = data.length;
      let start = range[1] ? Number(range[1]) : size - Number(range[2]);
      let end = range[1] && range[2] ? Number(range[2]) : size - 1;
      start = Math.max(0, start);
      end = Math.min(end, size - 1);
      if (start > end) {
        return new NextResponse(null, { status: 416, headers: { "Content-Range": `bytes */${size}` } });
      }
      const chunk = data.subarray(start, end + 1);
      headers["Content-Range"] = `bytes ${start}-${end}/${size}`;
      headers["Content-Length"] = String(chunk.length);
      return new NextResponse(new Uint8Array(chunk), { status: 206, headers });
    }
    headers["Content-Length"] = String(data.length);
    return new NextResponse(new Uint8Array(data), { headers });
  } catch (e) {
    return NextResponse.json({ error: `音声の取得に失敗しました: ${e instanceof Error ? e.message : e}` }, { status: 500 });
  }
}
