import { ChatPanel } from "@/components/chat-panel";
import { getDocument } from "@/lib/api";

export default async function DocumentPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const documentId = Number(id);
  let filename = `Document ${id}`;
  try {
    const doc = await getDocument(documentId);
    filename = doc.filename;
  } catch {
    filename = `Document ${id}`;
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{filename}</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Answers stay on this machine and cite the PDF.
        </p>
      </div>
      <ChatPanel documentId={documentId} />
    </main>
  );
}
