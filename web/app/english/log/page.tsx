import { isValidDate, todayJst } from "@/lib/date";
import { englishStore } from "@/lib/english/store";
import StudyLogPanel from "@/components/english/StudyLogPanel";

export const dynamic = "force-dynamic";

export default async function LogPage({ searchParams }: { searchParams: Promise<{ date?: string }> }) {
  const { date: q } = await searchParams;
  const date = isValidDate(q) ? q : todayJst();
  const logs = await englishStore().listStudyLogs(date);
  return <StudyLogPanel date={date} logs={logs} />;
}
