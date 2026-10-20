import TtsPlayer from "@/components/TtsPlayer";
import { SCORE_LABELS, type ScoreKey } from "@/lib/english/constants";
import type { Speech } from "@/lib/english/types";

const SUB_KEYS: ScoreKey[] = ["grammar", "vocabulary", "fluency", "content", "pronunciation"];

/** スピーチ分析結果（点数・成長メモ・総評・文字起こし・言い換え・自然な全文） */
export default function SpeechResult({ speech }: { speech: Speech }) {
  const s = speech.scores;
  return (
    <div className="flex flex-col gap-3">
      <div>
        <div className="text-xs text-gray-500">総合</div>
        <div className="text-3xl font-semibold">
          {s.total ?? "-"} <span className="text-base font-normal">点</span>
        </div>
        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-sm">
          {SUB_KEYS.map((k) => (
            <span key={k}>
              {SCORE_LABELS[k]} <b>{s[k] ?? "-"}</b>
            </span>
          ))}
        </div>
      </div>

      {speech.growthComment && <div className="alert alert-success">📈 成長メモ: {speech.growthComment}</div>}
      {speech.overallComment && <div className="alert alert-info">{speech.overallComment}</div>}

      <section>
        <h4 className="mb-1 text-sm font-bold">📝 文字起こし</h4>
        <p className="text-sm leading-relaxed">{speech.transcript}</p>
      </section>

      {speech.suggestions.length > 0 && (
        <section>
          <h4 className="mb-1 text-sm font-bold">💡 より自然な言い回し</h4>
          <ul className="flex flex-col gap-2 text-sm">
            {speech.suggestions.map((sg, i) => (
              <li key={i}>
                <span className="text-gray-400 line-through">{sg.original}</span> → <b>{sg.better}</b>
                <div className="text-xs text-gray-600">{sg.reason}</div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {speech.naturalVersion && (
        <details className="rounded-lg border border-gray-200 px-3 py-2">
          <summary className="cursor-pointer text-sm font-bold">✨ 自然な英語に直したスピーチ全文</summary>
          <div className="mt-2 flex flex-col gap-1">
            <TtsPlayer text={speech.naturalVersion} />
            <p className="text-sm leading-relaxed">{speech.naturalVersion}</p>
          </div>
        </details>
      )}
    </div>
  );
}
