import LoginButton from "./LoginButton";

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  const { error } = await searchParams;
  return (
    <div className="mt-16 flex flex-col items-center gap-6 text-center">
      <h1 className="text-2xl font-bold">Growth Log</h1>
      <p className="text-sm text-gray-500">からだと英語の記録</p>
      {error && (
        <div className="alert alert-error w-full">
          {error === "AccessDenied" ? "このアカウントではログインできません。" : "ログインに失敗しました。もう一度お試しください。"}
        </div>
      )}
      <LoginButton />
    </div>
  );
}
