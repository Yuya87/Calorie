export const dynamic = "force-dynamic";

export default function BodyPage() {
  const url = process.env.BODY_APP_URL;
  return (
    <div className="mt-6 flex flex-col gap-4">
      <h1 className="text-lg font-bold">🏋️ からだ（Body Make）</h1>
      <div className="alert alert-info">
        からだの記録は新しいアプリへ移行準備中です。移行が終わるまでは、現在のアプリをお使いください。
      </div>
      {url && (
        <a className="btn btn-primary self-start" href={url}>
          現在の Body Make アプリを開く
        </a>
      )}
    </div>
  );
}
