from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import select  # noqa: E402

from app.db.models import Document  # noqa: E402
from app.db.repositories import documents as docs_repo  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.jobs.ingest import ingest_document  # noqa: E402
from app.services.hashing import sha256_bytes  # noqa: E402
from app.services.ollama import OllamaClient  # noqa: E402
from app.services.retrieval import hybrid_search, vector_search  # noqa: E402
from app.services.storage import save_pdf  # noqa: E402


def _hit(chunks, relevant_pages: set[int]) -> bool:
    return any(chunk.page_number in relevant_pages for chunk in chunks)


async def _ensure_document(filename: str) -> int:
    fixture = ROOT / "tests" / "fixtures" / filename
    data = fixture.read_bytes()
    digest = sha256_bytes(data)
    async with SessionLocal() as session:
        existing = await session.scalar(
            select(Document).where(Document.content_sha256 == digest)
        )
        if existing is None:
            save_pdf(data, digest)
            existing = await docs_repo.create_document(
                session,
                filename=filename,
                content_sha256=digest,
                byte_size=len(data),
            )
        doc_id = existing.id
        status = existing.status
    if status != "ready":
        await ingest_document({}, doc_id)
    async with SessionLocal() as session:
        doc = await session.get(Document, doc_id)
        if doc is None or doc.status != "ready":
            raise SystemExit(
                f"document {doc_id} is not ready (status={getattr(doc, 'status', None)})"
            )
        return doc_id


async def main() -> int:
    parser = argparse.ArgumentParser(description="Compare vector vs hybrid retrieval")
    parser.add_argument(
        "--evalset",
        type=Path,
        default=ROOT / "tests" / "fixtures" / "evalset.json",
    )
    args = parser.parse_args()
    spec = json.loads(args.evalset.read_text(encoding="utf-8"))
    k = int(spec.get("k") or 8)
    await engine.dispose()
    doc_id = await _ensure_document(spec["documentFilename"])
    client = OllamaClient()
    vector_hits = 0
    hybrid_hits = 0
    rows: list[tuple[str, bool, bool]] = []
    async with SessionLocal() as session:
        for item in spec["queries"]:
            question = item["question"]
            relevant = set(item["relevantPageNumbers"])
            query_vec = (await client.embed([question]))[0]
            vector = await vector_search(
                session, query_vec, k=k, document_ids=[doc_id]
            )
            hybrid = await hybrid_search(
                session,
                question,
                query_vec=query_vec,
                fused_k=k,
                document_ids=[doc_id],
            )
            v_hit = _hit(vector[:k], relevant)
            h_hit = _hit(hybrid.fused[:k], relevant)
            vector_hits += int(v_hit)
            hybrid_hits += int(h_hit)
            rows.append((question, v_hit, h_hit))
    await engine.dispose()
    total = len(rows)
    print(f"{'query':<48} {'vector':<8} {'hybrid':<8}")
    print("-" * 68)
    for question, v_hit, h_hit in rows:
        print(f"{question[:48]:<48} {int(v_hit):<8} {int(h_hit):<8}")
    vector_rate = vector_hits / total if total else 0.0
    hybrid_rate = hybrid_hits / total if total else 0.0
    print("-" * 68)
    print(f"vector_hit@{k}: {vector_rate:.2f}  hybrid_hit@{k}: {hybrid_rate:.2f}")
    if hybrid_rate < vector_rate:
        print("warning: hybrid underperformed vector on this set")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
