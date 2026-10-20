import { addDays, mmdd, todayJst, weekStart } from "@/lib/date";
import { SKILLS } from "@/lib/english/constants";
import { englishStore } from "@/lib/english/store";
import ProgressCharts from "@/components/english/ProgressCharts";

export const dynamic = "force-dynamic";

const HEATMAP_WEEKS = 16;
const BAR_WEEKS = 12;

export default async function ProgressPage() {
  const logs = await englishStore().listAllStudyLogs();
  if (!logs.length) return <p className="text-sm text-gray-500">まだ勉強ログがありません。</p>;

  const today = todayJst();
  const daily = new Map<string, number>();
  for (const l of logs) daily.set(l.date, (daily.get(l.date) || 0) + l.minutes);

  // 連続記録日数（今日 or 昨日から遡って途切れるまで）
  let streak = 0;
  let cursor = (daily.get(today) || 0) > 0 ? today : addDays(today, -1);
  while ((daily.get(cursor) || 0) > 0) {
    streak++;
    cursor = addDays(cursor, -1);
  }
  const sumWhere = (pred: (d: string) => boolean) =>
    [...daily.entries()].filter(([d]) => pred(d)).reduce((s, [, m]) => s + m, 0);
  const totalMin = sumWhere(() => true);
  const monthMin = sumWhere((d) => d.slice(0, 7) === today.slice(0, 7));
  const weekMin = sumWhere((d) => d >= weekStart(today) && d <= today);

  // 日別ヒートマップ（過去16週・月曜始まり）: weeks[週][曜日] = 分（未来は null）
  const hmStart = addDays(weekStart(today), -7 * (HEATMAP_WEEKS - 1));
  const heatmap = Array.from({ length: HEATMAP_WEEKS }, (_, w) => {
    const ws = addDays(hmStart, 7 * w);
    return {
      label: mmdd(ws),
      days: Array.from({ length: 7 }, (_, wd) => {
        const d = addDays(ws, wd);
        return { date: d, minutes: d > today ? null : daily.get(d) || 0 };
      }),
    };
  });

  // 累計時間の推移
  let acc = 0;
  const cumulative = [...daily.keys()].sort().map((d) => {
    acc += daily.get(d) || 0;
    return { date: d, hours: Math.round((acc / 60) * 10) / 10 };
  });

  // 週ごとの技能別時間（過去12週）
  const barStart = addDays(weekStart(today), -7 * (BAR_WEEKS - 1));
  const weekly = Array.from({ length: BAR_WEEKS }, (_, i) => {
    const ws = addDays(barStart, 7 * i);
    const row: Record<string, number | string> = { week: `${mmdd(ws)}~` };
    for (const s of SKILLS) row[s] = 0;
    return row;
  });
  for (const l of logs) {
    if (l.date < barStart || l.date > today) continue;
    const idx = Math.floor((new Date(l.date).getTime() - new Date(barStart).getTime()) / (7 * 86400000));
    const row = weekly[idx];
    if (row && l.skill in row) row[l.skill] = Math.round(((row[l.skill] as number) + l.minutes / 60) * 10) / 10;
  }

  // 技能別の累計時間
  const bySkill = SKILLS.map((s) => ({
    skill: s,
    hours: Math.round((logs.filter((l) => l.skill === s).reduce((sum, l) => sum + l.minutes, 0) / 60) * 10) / 10,
  }));

  return (
    <ProgressCharts
      stats={{ total: totalMin / 60, month: monthMin / 60, week: weekMin / 60, streak }}
      heatmap={heatmap}
      cumulative={cumulative}
      weekly={weekly}
      bySkill={bySkill}
    />
  );
}
