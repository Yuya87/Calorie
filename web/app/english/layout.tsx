import EnglishTabs from "@/components/english/EnglishTabs";

export default function EnglishLayout({ children }: { children: React.ReactNode }) {
  return (
    <div>
      <h1 className="mb-2 text-lg font-bold">🗣️ English Growth Log</h1>
      <EnglishTabs />
      <div className="mt-3">{children}</div>
    </div>
  );
}
