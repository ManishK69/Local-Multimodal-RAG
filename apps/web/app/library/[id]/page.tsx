import { DocumentWorkspace } from "@/components/document-workspace";
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
    <main className="mx-auto flex min-h-0 w-full max-w-7xl flex-1 flex-col overflow-hidden px-4 py-4 sm:px-6">
      <div className="mb-3 shrink-0">
        <p className="text-primary text-xs font-medium tracking-[0.18em] uppercase">
          Reading desk
        </p>
        <h1 className="mt-1 truncate text-lg font-medium tracking-tight">{filename}</h1>
      </div>
      <DocumentWorkspace documentId={documentId} filename={filename} />
    </main>
  );
}
