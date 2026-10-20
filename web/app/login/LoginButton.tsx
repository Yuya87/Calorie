"use client";

import { signIn } from "next-auth/react";

export default function LoginButton() {
  return (
    <button className="btn btn-primary px-6 py-3 text-base" onClick={() => signIn("google", { callbackUrl: "/" })}>
      Google でログイン
    </button>
  );
}
