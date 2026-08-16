import { FolderDetail } from "@/components/folder-detail";

export default async function FolderPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const folderId = Number(id);

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-8 px-4 py-8 sm:px-6">
      <FolderDetail folderId={folderId} />
    </main>
  );
}
