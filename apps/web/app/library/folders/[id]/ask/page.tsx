import { redirect } from "next/navigation";

export default async function FolderAskPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  redirect(`/library/folders/${id}`);
}
