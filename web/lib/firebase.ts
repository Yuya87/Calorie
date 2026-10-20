import "server-only";
import { cert, getApps, initializeApp, type App } from "firebase-admin/app";
import { getFirestore } from "firebase-admin/firestore";
import { getStorage } from "firebase-admin/storage";

/** サービスアカウント（Streamlit の [gcp_service_account] と同じもの）で初期化 */
function getApp(): App {
  const existing = getApps();
  if (existing.length) return existing[0];
  const projectId = process.env.GCP_PROJECT_ID;
  const clientEmail = process.env.GCP_CLIENT_EMAIL;
  // Vercel の環境変数では改行が "\n" の文字列になっていることがあるため実際の改行に戻す
  const privateKey = (process.env.GCP_PRIVATE_KEY || "").replace(/\\n/g, "\n");
  if (!projectId || !clientEmail || !privateKey) {
    throw new Error("GCP_PROJECT_ID / GCP_CLIENT_EMAIL / GCP_PRIVATE_KEY が設定されていません。");
  }
  return initializeApp({ credential: cert({ projectId, clientEmail, privateKey }), projectId });
}

export function firestore() {
  return getFirestore(getApp());
}

export function englishAudioBucket() {
  const name = process.env.ENGLISH_AUDIO_BUCKET;
  if (!name) throw new Error("ENGLISH_AUDIO_BUCKET（音声保存用バケット名）が設定されていません。");
  return getStorage(getApp()).bucket(name);
}
