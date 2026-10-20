/**
 * ローカル開発用のダミーモード。
 * MOCK_BACKEND=1 のとき Firestore / Cloud Storage / Gemini / ログインを使わずメモリ上のダミーデータで動く。
 * Vercel 上（VERCEL=1）では常に無効。
 */
export const isMock = process.env.MOCK_BACKEND === "1" && process.env.VERCEL !== "1";
