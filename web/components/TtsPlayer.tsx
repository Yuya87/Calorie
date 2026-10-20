"use client";

import { useEffect, useRef, useState } from "react";

/**
 * 英文の読み上げ（ブラウザ内蔵の Web Speech API・米国英語）。
 * 速さ（0.5〜2.0倍）は localStorage に記憶し、画面内のすべての読み上げボタンで共通にする。
 */
const RATE_KEY = "tts_rate";
const RATE_EVENT = "tts-rate-change";
const PREFERRED_VOICES = ["Samantha", "Google US English", "Alex", "Aaron", "Nicky", "Microsoft Aria", "Microsoft Jenny"];

function loadRate(): number {
  try {
    const v = parseFloat(localStorage.getItem(RATE_KEY) || "");
    if (v >= 0.5 && v <= 2) return v;
  } catch {}
  return 1;
}

function pickVoice(): SpeechSynthesisVoice | null {
  const voices = window.speechSynthesis?.getVoices() || [];
  const us = voices.filter((v) => (v.lang || "").replace("_", "-").toLowerCase() === "en-us");
  for (const name of PREFERRED_VOICES) {
    const v = us.find((x) => x.name.includes(name));
    if (v) return v;
  }
  return us[0] || null;
}

export default function TtsPlayer({ text }: { text: string }) {
  const [rate, setRate] = useState(1);
  const [speaking, setSpeaking] = useState(false);
  const [unsupported, setUnsupported] = useState(false);
  const runId = useRef(0);

  useEffect(() => {
    setRate(loadRate());
    const onChange = (e: Event) => setRate((e as CustomEvent<number>).detail);
    window.addEventListener(RATE_EVENT, onChange);
    // 一部のブラウザは音声一覧を非同期で読み込むため、先に読み込みを促しておく
    window.speechSynthesis?.getVoices();
    return () => window.removeEventListener(RATE_EVENT, onChange);
  }, []);

  // 画面を離れたら読み上げを止める
  const speakingRef = useRef(false);
  speakingRef.current = speaking;
  useEffect(() => () => {
    if (speakingRef.current) window.speechSynthesis?.cancel();
  }, []);

  if (!text.trim()) return null;

  const changeRate = (v: number) => {
    setRate(v);
    try {
      localStorage.setItem(RATE_KEY, String(v));
    } catch {}
    window.dispatchEvent(new CustomEvent(RATE_EVENT, { detail: v }));
  };

  const toggle = () => {
    const synth = window.speechSynthesis;
    if (!synth) {
      setUnsupported(true);
      return;
    }
    if (speaking) {
      synth.cancel();
      setSpeaking(false);
      return;
    }
    synth.cancel();
    const id = ++runId.current;
    // 長文は途中で止まるブラウザがあるため、文ごとに分けて順番に読み上げる
    const sentences = (text.match(/[^.!?\n]+[.!?]*/g) || [text]).map((s) => s.trim()).filter(Boolean);
    const voice = pickVoice();
    sentences.forEach((s, i) => {
      const u = new SpeechSynthesisUtterance(s);
      u.lang = "en-US";
      if (voice) u.voice = voice;
      u.rate = rate;
      if (i === sentences.length - 1) u.onend = () => runId.current === id && setSpeaking(false);
      u.onerror = () => runId.current === id && setSpeaking(false);
      synth.speak(u);
    });
    setSpeaking(true);
  };

  return (
    <div className="flex items-center gap-2 py-1">
      <button type="button" className="btn shrink-0 whitespace-nowrap" onClick={toggle}>
        {unsupported ? "この端末は読み上げ非対応です" : speaking ? "⏹ 停止" : "🔊 読み上げ"}
      </button>
      <span className="shrink-0 text-xs text-gray-500">速さ</span>
      <input
        type="range"
        min={0.5}
        max={2}
        step={0.1}
        value={rate}
        onChange={(e) => changeRate(parseFloat(e.target.value))}
        className="min-w-[60px] max-w-[200px] flex-1"
        aria-label="読み上げの速さ"
      />
      <span className="w-9 shrink-0 text-xs text-gray-500">{rate.toFixed(1)}x</span>
    </div>
  );
}
