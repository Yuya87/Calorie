"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import TtsPlayer from "@/components/TtsPlayer";
import { addReadText, deleteReadText, updateReadText } from "@/lib/english/actions";
import type { ReadText } from "@/lib/english/types";

function TextItem({ item }: { item: ReadText }) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(item.title);
  const [text, setText] = useState(item.text);
  const [error, setError] = useState("");
  const [pending, start] = useTransition();
  const label = item.title || item.text.slice(0, 40) + (item.text.length > 40 ? "…" : "");

  const save = () =>
    start(async () => {
      const r = await updateReadText(item.id, title, text);
      if (r.ok) {
        setEditing(false);
        setError("");
        router.refresh();
      } else setError(r.error);
    });

  const remove = () =>
    start(async () => {
      const r = await deleteReadText(item.id);
      if (r.ok) router.refresh();
      else setError(r.error);
    });

  return (
    <details className="card">
      <summary className="cursor-pointer text-sm font-bold">{label}</summary>
      <div className="mt-2 flex flex-col gap-2">
        {editing ? (
          <>
            <label>
              <span className="label">タイトル（任意）</span>
              <input className="field" value={title} onChange={(e) => setTitle(e.target.value)} />
            </label>
            <label>
              <span className="label">英文</span>
              <textarea className="field" rows={6} value={text} onChange={(e) => setText(e.target.value)} />
            </label>
            <div className="flex gap-2">
              <button className="btn btn-primary" disabled={pending} onClick={save}>保存</button>
              <button className="btn" disabled={pending} onClick={() => setEditing(false)}>キャンセル</button>
            </div>
          </>
        ) : (
          <>
            <TtsPlayer text={item.text} />
            <p className="whitespace-pre-wrap text-sm leading-relaxed">{item.text}</p>
            <div className="flex gap-2">
              <button className="btn" onClick={() => setEditing(true)}>編集</button>
              <button className="btn btn-danger" disabled={pending} onClick={remove}>削除</button>
            </div>
          </>
        )}
        {error && <div className="alert alert-error">{error}</div>}
      </div>
    </details>
  );
}

export default function ReadPanel({ texts }: { texts: ReadText[] }) {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [message, setMessage] = useState<{ type: "success" | "warning" | "error"; text: string } | null>(null);
  const [pending, start] = useTransition();

  const save = () => {
    if (!text.trim()) {
      setMessage({ type: "warning", text: "英文を入力してください。" });
      return;
    }
    start(async () => {
      const r = await addReadText(title, text);
      if (r.ok) {
        // 保存に成功したら入力欄を空にする
        setTitle("");
        setText("");
        setMessage({ type: "success", text: "英文を保存しました！" });
        router.refresh();
      } else setMessage({ type: "error", text: r.error });
    });
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="card flex flex-col gap-3">
        <p className="text-xs text-gray-500">入力した英文を米国英語で読み上げます。速さは 0.5〜2.0 倍で調整でき、端末に記憶されます。</p>
        <label>
          <span className="label">タイトル（任意）</span>
          <input className="field" placeholder="例: 自己紹介、週末の出来事 など" value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <label>
          <span className="label">英文</span>
          <textarea
            className="field"
            rows={6}
            placeholder="例: Last weekend, I went hiking with my family."
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </label>
        <TtsPlayer text={text} />
        <button className="btn btn-primary self-start" disabled={pending} onClick={save}>
          {pending ? "保存中..." : "英文を保存"}
        </button>
        {message && <div className={`alert alert-${message.type}`}>{message.text}</div>}
      </div>

      <section className="flex flex-col gap-2">
        <h2 className="text-base font-bold">保存した英文</h2>
        {texts.length ? (
          texts.map((t) => <TextItem key={t.id + t.title + t.text} item={t} />)
        ) : (
          <p className="text-sm text-gray-500">保存した英文はありません。</p>
        )}
      </section>
    </div>
  );
}
