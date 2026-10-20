"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { SCORE_KEYS, SCORE_LABELS, type ScoreKey } from "@/lib/english/constants";
import { deleteSpeech } from "@/lib/english/actions";
import type { Speech } from "@/lib/english/types";
import SpeechResult from "./SpeechResult";

// 点数の推移の線の色（検証済みカテゴリ配色の先頭6色）
const LINE_COLORS: Record<ScoreKey, string> = {
  total: "#2a78d6",
  grammar: "#eb6834",
  vocabulary: "#1baf7a",
  fluency: "#eda100",
  content: "#e87ba4",
  pronunciation: "#008300",
};
const AXIS = { fontSize: 11, fill: "#6b7280" };

function SpeechItem({ speech }: { speech: Speech }) {
  const router = useRouter();
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState("");
  const [pending, start] = useTransition();
  const audioUrl = `/api/english/speeches/${speech.id}/audio`;

  const remove = () =>
    start(async () => {
      const r = await deleteSpeech(speech.id);
      if (r.ok) router.refresh();
      else setError(r.error);
    });

  return (
    <details className="card">
      <summary className="cursor-pointer text-sm font-bold">
        {speech.date}（総合 {speech.scores.total ?? "-"} 点）
      </summary>
      <div className="mt-3 flex flex-col gap-3">
        {speech.audioPath && (
          <div className="flex flex-col gap-2">
            <audio controls preload="none" src={audioUrl} className="w-full" />
            <a className="btn self-start" href={`${audioUrl}?download=1`}>
              ⬇️ 音声をダウンロード
            </a>
          </div>
        )}
        <SpeechResult speech={speech} />
        <div className="border-t border-gray-200 pt-3">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />
            このスピーチを削除する
          </label>
          {confirm && (
            <button className="btn btn-danger mt-2" disabled={pending} onClick={remove}>
              削除を実行（音声も削除されます）
            </button>
          )}
          {error && <div className="alert alert-error mt-2">{error}</div>}
        </div>
      </div>
    </details>
  );
}

export default function SpeechHistory({ speeches }: { speeches: Speech[] }) {
  const [shown, setShown] = useState<ScoreKey[]>(["total"]);
  const data = speeches.map((s) => ({ date: s.date, ...s.scores }));
  const toggle = (k: ScoreKey) => setShown((cur) => (cur.includes(k) ? cur.filter((x) => x !== k) : [...cur, k]));

  return (
    <div className="flex flex-col gap-4">
      <section className="card">
        <h2 className="mb-2 text-sm font-bold">点数の推移</h2>
        <div className="mb-2 flex flex-wrap gap-1.5">
          {SCORE_KEYS.map((k) => (
            <button key={k} type="button" className="chip" aria-pressed={shown.includes(k)} onClick={() => toggle(k)}>
              {SCORE_LABELS[k]}
            </button>
          ))}
        </div>
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={data} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
            <CartesianGrid stroke="#eef0f2" vertical={false} />
            <XAxis dataKey="date" tick={AXIS} tickFormatter={(d: string) => d.slice(5).replace("-", "/")} />
            <YAxis domain={[0, 100]} tick={AXIS} />
            <Tooltip />
            {shown.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} />}
            {SCORE_KEYS.filter((k) => shown.includes(k)).map((k) => (
              <Line
                key={k}
                type="monotone"
                dataKey={k}
                name={SCORE_LABELS[k]}
                stroke={LINE_COLORS[k]}
                strokeWidth={2}
                dot={{ r: 4 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-base font-bold">過去のスピーチ</h2>
        {[...speeches].reverse().map((s) => (
          <SpeechItem key={s.id} speech={s} />
        ))}
      </section>
    </div>
  );
}
