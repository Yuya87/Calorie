"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { weekdayLabel } from "@/lib/date";
import { SKILLS } from "@/lib/english/constants";
import { addStudyLog, deleteStudyLog, updateStudyLog } from "@/lib/english/actions";
import type { StudyLog } from "@/lib/english/types";

function SkillPicker({ value, onChange, name }: { value: string; onChange: (s: string) => void; name: string }) {
  return (
    <div role="radiogroup" aria-label="技能" className="flex flex-wrap gap-1.5">
      {SKILLS.map((s) => (
        <button
          key={s}
          type="button"
          role="radio"
          name={name}
          aria-checked={value === s}
          className="chip"
          onClick={() => onChange(s)}
        >
          {s}
        </button>
      ))}
    </div>
  );
}

function LogItem({ log }: { log: StudyLog }) {
  const [editing, setEditing] = useState(false);
  const [minutes, setMinutes] = useState(String(log.minutes));
  const [skill, setSkill] = useState(log.skill);
  const [content, setContent] = useState(log.content);
  const [error, setError] = useState("");
  const [pending, start] = useTransition();
  const router = useRouter();

  const save = () =>
    start(async () => {
      const r = await updateStudyLog(log.id, { minutes: Number(minutes), skill, content });
      if (r.ok) {
        setEditing(false);
        setError("");
        router.refresh();
      } else setError(r.error);
    });

  const remove = () =>
    start(async () => {
      const r = await deleteStudyLog(log.id);
      if (r.ok) router.refresh();
      else setError(r.error);
    });

  return (
    <li className="card flex flex-col gap-2">
      <div className="text-sm">
        <b>[{log.skill}]</b> {log.minutes} 分　{log.content}
      </div>
      {editing ? (
        <div className="flex flex-col gap-2">
          <label>
            <span className="label">勉強時間 (分)</span>
            <input className="field" type="number" min={1} max={600} step={5} value={minutes} onChange={(e) => setMinutes(e.target.value)} />
          </label>
          <SkillPicker value={skill} onChange={setSkill} name={`skill-${log.id}`} />
          <label>
            <span className="label">勉強内容</span>
            <input className="field" value={content} onChange={(e) => setContent(e.target.value)} />
          </label>
          <div className="flex gap-2">
            <button className="btn btn-primary" disabled={pending} onClick={save}>保存</button>
            <button className="btn" disabled={pending} onClick={() => setEditing(false)}>キャンセル</button>
          </div>
        </div>
      ) : (
        <div className="flex gap-2">
          <button className="btn" onClick={() => setEditing(true)}>編集</button>
          <button className="btn btn-danger" disabled={pending} onClick={remove}>削除</button>
        </div>
      )}
      {error && <div className="alert alert-error">{error}</div>}
    </li>
  );
}

export default function StudyLogPanel({ date, logs }: { date: string; logs: StudyLog[] }) {
  const router = useRouter();
  const [minutes, setMinutes] = useState("30");
  const [skill, setSkill] = useState("");
  const [content, setContent] = useState("");
  const [message, setMessage] = useState<{ type: "success" | "warning" | "error"; text: string } | null>(null);
  const [pending, start] = useTransition();
  const total = logs.reduce((sum, l) => sum + l.minutes, 0);

  const save = () => {
    if (!skill) {
      setMessage({ type: "warning", text: "技能を1つ選択してください。" });
      return;
    }
    start(async () => {
      const r = await addStudyLog({ date, minutes: Number(minutes), skill, content });
      if (r.ok) {
        // 保存に成功したら入力欄を初期状態に戻す
        setMinutes("30");
        setSkill("");
        setContent("");
        setMessage({ type: "success", text: "勉強ログを保存しました！" });
        router.refresh();
      } else setMessage({ type: "error", text: r.error });
    });
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="card flex flex-col gap-3">
        <label>
          <span className="label">記録対象日</span>
          <input
            className="field"
            type="date"
            value={date}
            onChange={(e) => e.target.value && router.push(`/english/log?date=${e.target.value}`)}
          />
        </label>
        <div className="alert alert-info">
          選択中: {date} ({weekdayLabel(date)})
        </div>
        <label>
          <span className="label">勉強時間 (分)</span>
          <input className="field" type="number" min={1} max={600} step={5} value={minutes} onChange={(e) => setMinutes(e.target.value)} />
        </label>
        <div>
          <span className="label">技能（学習の目的で1つ選択）</span>
          <SkillPicker value={skill} onChange={setSkill} name="skill-new" />
        </div>
        <label>
          <span className="label">勉強内容</span>
          <input
            className="field"
            placeholder="例: Podcastをシャドーイング、オンライン英会話 など"
            value={content}
            onChange={(e) => setContent(e.target.value)}
          />
        </label>
        <button className="btn btn-primary self-start" disabled={pending} onClick={save}>
          {pending ? "保存中..." : "勉強ログを保存"}
        </button>
        {message && <div className={`alert alert-${message.type}`}>{message.text}</div>}
      </div>

      <section>
        <h2 className="mb-2 text-base font-bold">この日の記録（合計 {total} 分）</h2>
        {logs.length ? (
          <ul className="flex flex-col gap-2">
            {logs.map((l) => (
              <LogItem key={l.id + l.minutes + l.skill + l.content} log={l} />
            ))}
          </ul>
        ) : (
          <p className="text-sm text-gray-500">この日の勉強ログはありません。</p>
        )}
      </section>
    </div>
  );
}
