"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { AUDIO_TYPES, MAX_UPLOAD_BYTES } from "@/lib/english/constants";
import type { Speech, SpeechJob } from "@/lib/english/types";
import { convertToWav16k } from "@/lib/english/wav";
import SpeechResult from "./SpeechResult";

type Props = {
  today: string;
  doneThisWeek: boolean;
  latest: Speech | null;
  runningJobId: string | null;
  runningJobStartedAt: string | null;
};

export default function SpeechPanel({ today, doneThisWeek, latest, runningJobId, runningJobStartedAt }: Props) {
  const router = useRouter();
  const [date, setDate] = useState(today);
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [phase, setPhase] = useState<"idle" | "converting" | "uploading">("idle");
  const [jobId, setJobId] = useState<string | null>(runningJobId);
  const [startedAt, setStartedAt] = useState<number>(runningJobStartedAt ? new Date(runningJobStartedAt).getTime() : 0);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!file) return;
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  // 分析ジョブの進み具合を3秒ごとに確認する（画面を開き直しても、実行中のジョブがあれば続きから表示）
  useEffect(() => {
    if (!jobId) return;
    let stopped = false;
    const tick = async () => {
      setElapsed(Math.floor((Date.now() - (startedAt || Date.now())) / 1000));
      try {
        const res = await fetch(`/api/english/jobs/${jobId}`, { cache: "no-store" });
        if (!res.ok) return;
        const job: SpeechJob = await res.json();
        if (stopped || job.status === "running") return;
        setJobId(null);
        if (job.status === "done") {
          setFile(null);
          if (fileInput.current) fileInput.current.value = "";
          router.replace(`/english/speech?done=${job.speechId}`);
          router.refresh();
        } else {
          setError(job.error || "分析に失敗しました。");
        }
      } catch {
        // 通信が一時的に切れても次の確認で再開する
      }
    };
    tick();
    const timer = setInterval(tick, 3000);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [jobId, startedAt, router]);

  const analyze = async () => {
    if (!file) return;
    setError("");
    const ext = (file.name.split(".").pop() || "").toLowerCase();
    if (!AUDIO_TYPES[ext]) {
      setError("対応していない音声形式です（m4a / mp3 / wav / aac）。");
      return;
    }
    try {
      setPhase("converting");
      const wav = await convertToWav16k(file).catch((e) => {
        throw new Error(`この端末のブラウザでは音声を変換できませんでした。別の形式（m4a / mp3 / wav）でお試しください。（${e instanceof Error ? e.message : e}）`);
      });
      if (file.size + wav.size > MAX_UPLOAD_BYTES) throw new Error("音声が長すぎます（目安: 2分以内）。");
      setPhase("uploading");
      const form = new FormData();
      form.append("original", file, file.name);
      form.append("wav", wav, "speech.wav");
      form.append("date", date);
      const res = await fetch("/api/english/speeches", { method: "POST", body: form });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.error || `アップロードに失敗しました（${res.status}）。`);
      setStartedAt(Date.now());
      setElapsed(0);
      setJobId(body.jobId);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPhase("idle");
    }
  };

  const busy = phase !== "idle" || !!jobId;

  return (
    <div className="flex flex-col gap-4">
      {doneThisWeek ? (
        <div className="alert alert-success">✅ 今週のスピーチは録音済みです。</div>
      ) : (
        <div className="alert alert-warning">🎙️ 今週はまだ録音していません。</div>
      )}

      <div className="card flex flex-col gap-3">
        <label>
          <span className="label">スピーチ日</span>
          <input className="field" type="date" value={date} onChange={(e) => e.target.value && setDate(e.target.value)} />
        </label>
        <label>
          <span className="label">ボイスメモの音声ファイル（m4a / mp3 / wav など）</span>
          <input
            ref={fileInput}
            type="file"
            accept="audio/*,.m4a,.mp3,.wav,.aac"
            className="text-sm"
            disabled={busy}
            onChange={(e) => {
              setFile(e.target.files?.[0] || null);
              setError("");
            }}
          />
        </label>
        {file && previewUrl && <audio controls src={previewUrl} className="w-full" />}
        <button className="btn btn-primary self-start" disabled={!file || busy} onClick={analyze}>
          AIで分析して保存
        </button>
        {phase === "converting" && <div className="alert alert-info">⏳ 音声を変換中...</div>}
        {phase === "uploading" && <div className="alert alert-info">⏳ 音声を送信中...</div>}
        {jobId && (
          <div className="alert alert-info">
            ⏳ Geminiがスピーチを分析・保存中...（{elapsed}秒経過。1分ほどかかります。画面を閉じても分析は続きます）
          </div>
        )}
        {error && <div className="alert alert-error">{error}</div>}
      </div>

      {latest && (
        <section className="card">
          <h2 className="mb-2 text-base font-bold">分析結果（{latest.date}）</h2>
          <SpeechResult speech={latest} />
        </section>
      )}
    </div>
  );
}
