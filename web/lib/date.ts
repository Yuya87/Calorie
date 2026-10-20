/** 日付は "YYYY-MM-DD" 文字列で扱う。「今日」は日本時間で判定する（サーバーは UTC のため）。 */

export const WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"];

export function todayJst(): string {
  return new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Tokyo" }).format(new Date());
}

function toUtc(dateStr: string): Date {
  const [y, m, d] = dateStr.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

function fromUtc(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function addDays(dateStr: string, days: number): string {
  const d = toUtc(dateStr);
  d.setUTCDate(d.getUTCDate() + days);
  return fromUtc(d);
}

/** 月曜=0 … 日曜=6 */
export function weekdayIndex(dateStr: string): number {
  return (toUtc(dateStr).getUTCDay() + 6) % 7;
}

export function weekdayLabel(dateStr: string): string {
  return WEEKDAYS[weekdayIndex(dateStr)];
}

/** その週の月曜日 */
export function weekStart(dateStr: string): string {
  return addDays(dateStr, -weekdayIndex(dateStr));
}

export function daysBetween(a: string, b: string): number {
  return Math.round((toUtc(b).getTime() - toUtc(a).getTime()) / 86400000);
}

export function isValidDate(s: string | undefined | null): s is string {
  return !!s && /^\d{4}-\d{2}-\d{2}$/.test(s) && !Number.isNaN(toUtc(s).getTime());
}

/** "MM/DD" */
export function mmdd(dateStr: string): string {
  return `${dateStr.slice(5, 7)}/${dateStr.slice(8, 10)}`;
}
