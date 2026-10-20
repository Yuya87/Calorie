import { todayJst, weekStart } from "@/lib/date";
import { englishStore } from "@/lib/english/store";
import SpeechPanel from "@/components/english/SpeechPanel";

export const dynamic = "force-dynamic";

export default async function SpeechPage({ searchParams }: { searchParams: Promise<{ done?: string }> }) {
  const { done } = await searchParams;
  const store = englishStore();
  const [speeches, runningJob] = await Promise.all([store.listSpeeches(), store.findRunningJob()]);
  const today = todayJst();
  const thisWeek = speeches.filter((s) => s.date >= weekStart(today));
  // 直前に分析したスピーチ、なければ今週保存済みの最新スピーチを表示する
  const latest = (done && speeches.find((s) => s.id === done)) || thisWeek[thisWeek.length - 1] || null;
  return (
    <SpeechPanel
      today={today}
      doneThisWeek={thisWeek.length > 0}
      latest={latest}
      runningJobId={runningJob?.id || null}
      runningJobStartedAt={runningJob?.startedAt || null}
    />
  );
}
