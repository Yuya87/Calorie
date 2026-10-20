import { englishStore } from "@/lib/english/store";
import SpeechHistory from "@/components/english/SpeechHistory";

export const dynamic = "force-dynamic";

export default async function HistoryPage() {
  const speeches = await englishStore().listSpeeches();
  if (!speeches.length) return <p className="text-sm text-gray-500">まだスピーチの記録がありません。</p>;
  return <SpeechHistory speeches={speeches} />;
}
