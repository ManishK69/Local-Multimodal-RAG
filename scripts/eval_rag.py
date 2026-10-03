from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.db.models import Chunk  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.eval.documents import ensure_document_ready  # noqa: E402
from app.eval.gold import GoldQuestion, GoldSet, load_gold_set  # noqa: E402
from app.eval.retrieval_metrics import evaluate_ranking, summarize  # noqa: E402
from app.services.ollama import OllamaClient  # noqa: E402
from app.services.retrieval import (  # noqa: E402
    RankedChunk,
    hybrid_search,
    lexical_search,
    vector_search,
)
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

VARIANTS = ("vector", "lexical", "hybrid")
FIXTURE_DIR = ROOT / "tests" / "fixtures"


async def _chunk_keys(
    session: AsyncSession, chunks: list[RankedChunk]
) -> list[tuple[int, int]]:
    """Map retrieved chunks to (page_number, chunk_index) gold keys."""
    ids = [chunk.chunk_id for chunk in chunks]
    if not ids:
        return []
    rows = await session.execute(
        select(Chunk.id, Chunk.chunk_index).where(Chunk.id.in_(ids))
    )
    index_by_id = dict(rows.all())
    return [
        (chunk.page_number, index_by_id[chunk.chunk_id])
        for chunk in chunks
        if chunk.chunk_id in index_by_id
    ]


async def _run_variant(
    session: AsyncSession,
    variant: str,
    question: GoldQuestion,
    query_vec: list[float],
    doc_id: int,
    k: int,
) -> list[RankedChunk]:
    if variant == "vector":
        return await vector_search(session, query_vec, k=k, document_ids=[doc_id])
    if variant == "lexical":
        return await lexical_search(
            session, question.question, k=k, document_ids=[doc_id]
        )
    result = await hybrid_search(
        session,
        question.question,
        query_vec=query_vec,
        k_vector=k,
        k_lexical=k,
        fused_k=k,
        document_ids=[doc_id],
    )
    return result.fused


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate retrieval variants against a gold question set"
    )
    parser.add_argument(
        "--gold",
        type=Path,
        default=ROOT / "tests" / "fixtures" / "eval" / "gold.v1.json",
    )
    parser.add_argument(
        "--variants",
        nargs="+",
        choices=VARIANTS,
        default=list(VARIANTS),
    )
    parser.add_argument("--k", type=int, default=None)
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=ROOT / "eval" / "reports",
    )
    args = parser.parse_args()

    gold: GoldSet = load_gold_set(args.gold)
    k = args.k or gold.k
    print(
        f"gold set: {gold.name} ({gold.version}), "
        f"{len(gold.questions)} questions, k={k}"
    )
    print(f"chunking the labels assume: {gold.chunking}")

    await engine.dispose()
    doc_ids: dict[str, int] = {}
    for filename in {q.document_filename for q in gold.questions}:
        doc_ids[filename] = await ensure_document_ready(FIXTURE_DIR, filename)

    answerable = [q for q in gold.questions if q.relevant_chunks]
    skipped = len(gold.questions) - len(answerable)
    if skipped:
        print(
            f"skipping {skipped} unanswerable question(s) for retrieval metrics "
            "(kept for generation eval)"
        )

    client = OllamaClient()
    # Embed once; reuse the vector across variants.
    query_vecs = await client.embed([q.question for q in answerable])

    per_variant: dict[str, list[dict[str, float]]] = {
        variant: [] for variant in args.variants
    }
    rows: list[dict] = []
    async with SessionLocal() as session:
        for question, query_vec in zip(answerable, query_vecs):
            doc_id = doc_ids[question.document_filename]
            relevant = question.relevant_keys()
            row: dict = {"id": question.id, "variants": {}}
            for variant in args.variants:
                chunks = await _run_variant(
                    session, variant, question, query_vec, doc_id, k
                )
                keys = await _chunk_keys(session, chunks)
                metrics = evaluate_ranking(keys, relevant, k)
                per_variant[variant].append(metrics)
                row["variants"][variant] = metrics
            rows.append(row)
    await engine.dispose()

    aggregate = {
        variant: summarize(results) for variant, results in per_variant.items()
    }

    metric_names = [f"hit@{k}", f"recall@{k}", "mrr"]
    header = f"{'variant':<10}" + "".join(f"{name:>12}" for name in metric_names)
    header += f"{'n':>6}"
    print(header)
    print("-" * len(header))
    for variant in args.variants:
        agg = aggregate[variant]
        cells = "".join(f"{agg[name]:>12.3f}" for name in metric_names)
        print(f"{variant:<10}{cells}{len(per_variant[variant]):>6}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = args.report_dir / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "gold_set": {
            "path": str(args.gold),
            "name": gold.name,
            "version": gold.version,
            "chunking": gold.chunking,
        },
        "k": k,
        "variants": list(args.variants),
        "questions": rows,
        "aggregate": aggregate,
    }
    out_path = out_dir / "results.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nreport written to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
