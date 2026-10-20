import type { Metadata, Viewport } from "next";
import "./globals.css";
import BottomNav from "@/components/BottomNav";

export const metadata: Metadata = {
  title: "Growth Log",
  description: "からだと英語の記録",
  appleWebApp: { capable: true, title: "Growth Log", statusBarStyle: "default" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#f7f7f5",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body className="min-h-dvh">
        <div className="mx-auto max-w-screen-sm px-4 pt-3 pb-24">{children}</div>
        <BottomNav />
      </body>
    </html>
  );
}
