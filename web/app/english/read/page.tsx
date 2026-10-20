import { englishStore } from "@/lib/english/store";
import ReadPanel from "@/components/english/ReadPanel";

export const dynamic = "force-dynamic";

export default async function ReadPage() {
  const texts = await englishStore().listReadTexts();
  return <ReadPanel texts={texts} />;
}
