import { LibraryFolders } from "@/components/library-folders";
import { UploadDropzone } from "@/components/upload-dropzone";

export default function LibraryPage() {
  return (
    <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-8 px-4 py-8 sm:px-6">
      <div className="enter-up max-w-xl">
        <p className="text-primary mb-2 text-xs font-medium tracking-[0.18em] uppercase">
          Library
        </p>
        <h1 className="font-heading text-3xl tracking-tight italic sm:text-4xl">
          Your private shelf
        </h1>
        <p className="text-muted-foreground mt-2 max-w-md text-sm leading-relaxed">
          Drop a PDF, or group related files in a folder and ask across the set.
          Nothing leaves this machine.
        </p>
      </div>
      <LibraryFolders />
      <UploadDropzone
        unfiled
        heading="Documents"
        emptyLabel="PDFs outside a folder live here. Open one to ask about that file only."
      />
    </main>
  );
}
