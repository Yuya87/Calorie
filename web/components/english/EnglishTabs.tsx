"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/english/log", label: "📝 勉強ログ" },
  { href: "/english/speech", label: "🎤 1分スピーチ" },
  { href: "/english/progress", label: "📈 積み上げ" },
  { href: "/english/history", label: "🎧 スピーチ履歴" },
  { href: "/english/read", label: "🔊 読み上げ" },
];

export default function EnglishTabs() {
  const pathname = usePathname();
  return (
    <nav className="-mx-4 flex gap-1 overflow-x-auto border-b border-gray-200 px-4">
      {TABS.map((t) => {
        const active = pathname.startsWith(t.href);
        return (
          <Link
            key={t.href}
            href={t.href}
            className={`shrink-0 whitespace-nowrap border-b-2 px-2 py-2 text-sm ${
              active ? "border-[var(--accent)] font-bold text-[var(--accent)]" : "border-transparent text-gray-600"
            }`}
          >
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
