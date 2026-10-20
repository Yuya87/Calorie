import { NextResponse, type NextFetchEvent, type NextRequest } from "next/server";
import { withAuth, type NextRequestWithAuth } from "next-auth/middleware";

const isMock = process.env.MOCK_BACKEND === "1" && process.env.VERCEL !== "1";

/** ログインしていなければ /login へ */
const authMiddleware = withAuth({
  pages: { signIn: "/login" },
  callbacks: { authorized: ({ token }) => !!token },
});

export default function middleware(req: NextRequest, event: NextFetchEvent) {
  // ローカル開発のダミーモードではログイン確認をしない
  if (isMock) return NextResponse.next();
  return authMiddleware(req as NextRequestWithAuth, event);
}

export const config = {
  // ログイン画面・認証API・静的ファイル・PWA用ファイル以外をすべて保護する
  matcher: ["/((?!api/auth|login|_next/static|_next/image|favicon.ico|manifest.webmanifest|icon|apple-icon).*)"],
};
