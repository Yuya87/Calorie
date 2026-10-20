"use client";

import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { WEEKDAYS } from "@/lib/date";
import { SKILL_COLORS, SKILLS } from "@/lib/english/constants";

type Props = {
  stats: { total: number; month: number; week: number; streak: number };
  heatmap: { label: string; days: { date: string; minutes: number | null }[] }[];
  cumulative: { date: string; hours: number }[];
  weekly: Record<string, number | string>[];
  bySkill: { skill: string; hours: number }[];
};

const AXIS = { fontSize: 11, fill: "#6b7280" };

/** 勉強時間（分）→ 色（1色の濃淡。0分は薄いグレー） */
function heatColor(m: number | null, max: number) {
  if (m === null) return "transparent";
  if (m <= 0) return "#ebedf0";
  const steps = ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#104281"];
  return steps[Math.min(steps.length - 1, Math.floor((m / max) * steps.length))];
}

function Heatmap({ weeks }: { weeks: Props["heatmap"] }) {
  const [hover, setHover] = useState<{ date: string; minutes: number } | null>(null);
  const max = Math.max(90, ...weeks.flatMap((w) => w.days.map((d) => d.minutes || 0)));
  const cell = 16;
  const gap = 3;
  const left = 18;
  const top = 30;
  const width = left + weeks.length * (cell + gap);
  const height = top + 7 * (cell + gap);
  return (
    <div>
      <div className="overflow-x-auto">
        <svg width={width} height={height} role="img" aria-label="日別の勉強時間">
          {weeks.map((w, i) =>
            i % 2 === 0 ? (
              <text
                key={w.label}
                x={left + i * (cell + gap) + cell / 2}
                y={top - 6}
                fontSize={9}
                fill="#6b7280"
                textAnchor="start"
                transform={`rotate(-60 ${left + i * (cell + gap) + cell / 2} ${top - 6})`}
              >
                {w.label}
              </text>
            ) : null,
          )}
          {WEEKDAYS.map((d, i) => (
            <text key={d} x={0} y={top + i * (cell + gap) + cell - 4} fontSize={10} fill="#6b7280">
              {d}
            </text>
          ))}
          {weeks.map((w, i) =>
            w.days.map((d, j) =>
              d.minutes === null ? null : (
                <rect
                  key={d.date}
                  x={left + i * (cell + gap)}
                  y={top + j * (cell + gap)}
                  width={cell}
                  height={cell}
                  rx={3}
                  fill={heatColor(d.minutes, max)}
                  onMouseEnter={() => setHover({ date: d.date, minutes: d.minutes || 0 })}
                  onClick={() => setHover({ date: d.date, minutes: d.minutes || 0 })}
                >
                  <title>{`${d.date} (${WEEKDAYS[j]}) ${d.minutes} 分`}</title>
                </rect>
              ),
            ),
          )}
        </svg>
      </div>
      <div className="mt-1 h-5 text-xs text-gray-600">{hover ? `${hover.date}: ${hover.minutes} 分` : "マスをタップすると時間を表示"}</div>
    </div>
  );
}

export default function ProgressCharts({ stats, heatmap, cumulative, weekly, bySkill }: Props) {
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-2">
        {[
          ["累計", `${stats.total.toFixed(1)} 時間`],
          ["今月", `${stats.month.toFixed(1)} 時間`],
          ["今週", `${stats.week.toFixed(1)} 時間`],
          ["連続記録", `${stats.streak} 日`],
        ].map(([label, value]) => (
          <div key={label} className="card">
            <div className="text-xs text-gray-500">{label}</div>
            <div className="text-2xl font-semibold">{value}</div>
          </div>
        ))}
      </div>

      <section className="card">
        <h2 className="mb-2 text-sm font-bold">日別の勉強時間（過去16週）</h2>
        <Heatmap weeks={heatmap} />
      </section>

      <section className="card">
        <h2 className="mb-2 text-sm font-bold">累計勉強時間の推移</h2>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={cumulative} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
            <CartesianGrid stroke="#eef0f2" vertical={false} />
            <XAxis dataKey="date" tick={AXIS} tickFormatter={(d: string) => d.slice(5).replace("-", "/")} minTickGap={24} />
            <YAxis tick={AXIS} />
            <Tooltip formatter={(v) => [`${v} 時間`, "累計"]} />
            <Line type="monotone" dataKey="hours" stroke="#2a78d6" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </section>

      <section className="card">
        <h2 className="mb-2 text-sm font-bold">週ごとの技能別時間（過去12週）</h2>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={weekly} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
            <CartesianGrid stroke="#eef0f2" vertical={false} />
            <XAxis dataKey="week" tick={AXIS} interval={1} />
            <YAxis tick={AXIS} />
            <Tooltip formatter={(v, name) => [`${v} 時間`, name]} />
            <Legend wrapperStyle={{ fontSize: 11 }} itemSorter={(item) => SKILLS.indexOf(String(item.value) as (typeof SKILLS)[number])} />
            {SKILLS.map((s) => (
              <Bar key={s} dataKey={s} stackId="a" fill={SKILL_COLORS[s]} stroke="#fff" strokeWidth={1} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </section>

      <section className="card">
        <h2 className="mb-2 text-sm font-bold">技能別の累計時間</h2>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={bySkill} layout="vertical" margin={{ top: 0, right: 40, left: 10, bottom: 0 }}>
            <XAxis type="number" tick={AXIS} />
            <YAxis type="category" dataKey="skill" tick={AXIS} width={70} />
            <Tooltip formatter={(v) => [`${v} 時間`, "累計"]} />
            <Bar dataKey="hours" radius={[0, 4, 4, 0]}>
              {bySkill.map((b) => (
                <Cell key={b.skill} fill={SKILL_COLORS[b.skill]} />
              ))}
              <LabelList dataKey="hours" position="right" formatter={(v) => `${v}h`} style={{ fontSize: 11, fill: "#374151" }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </section>
    </div>
  );
}
