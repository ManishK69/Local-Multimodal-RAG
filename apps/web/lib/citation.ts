import type { Citation } from "@/lib/api";

const KEY = "lmrag:pending-citation";

export function stashCitation(citation: Citation) {
  sessionStorage.setItem(KEY, JSON.stringify(citation));
}

export function takePendingCitation(documentId: number): Citation | null {
  const raw = sessionStorage.getItem(KEY);
  if (!raw) return null;
  sessionStorage.removeItem(KEY);
  try {
    const citation = JSON.parse(raw) as Citation;
    if (citation.documentId !== documentId) return null;
    return citation;
  } catch {
    return null;
  }
}
