import { NextResponse } from "next/server";
import { requireUser } from "@/lib/session";
import { englishStore } from "@/lib/english/store";

export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    await requireUser();
  } catch {
    return NextResponse.json({ error: "ログインが必要です。" }, { status: 401 });
  }
  const { id } = await params;
  const job = await englishStore().getJob(id);
  if (!job) return NextResponse.json({ error: "ジョブが見つかりません。" }, { status: 404 });
  return NextResponse.json(job, { headers: { "Cache-Control": "no-store" } });
}
