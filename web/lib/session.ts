import "server-only";
import { getServerSession } from "next-auth";
import { authOptions } from "./auth";
import { isMock } from "./env";

/** Server Action / Route Handler の先頭で呼ぶ。未ログインなら例外 */
export async function requireUser(): Promise<void> {
  if (isMock) return;
  const session = await getServerSession(authOptions);
  if (!session?.user?.email) throw new Error("ログインが必要です。");
}
