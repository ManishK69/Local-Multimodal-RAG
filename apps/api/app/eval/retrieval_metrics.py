from __future__ import annotations

# A chunk key is a (page_number, chunk_index) pair, matching
# GoldQuestion.relevant_keys(). chunk_index is the value persisted on
# chunks.chunk_index, which is stable for a given chunker configuration.
ChunkKey = tuple[int, int]


def hit_at_k(
    ranked: list[ChunkKey], relevant: set[ChunkKey], k: int
) -> bool:
    """Whether at least one relevant chunk is ranked in the top k."""
    return any(key in relevant for key in ranked[:k])


def recall_at_k(
    ranked: list[ChunkKey], relevant: set[ChunkKey], k: int
) -> float:
    """Fraction of relevant chunks retrieved in the top k."""
    if not relevant:
        raise ValueError("relevant must be non-empty")
    return sum(1 for key in ranked[:k] if key in relevant) / len(relevant)


def reciprocal_rank(
    ranked: list[ChunkKey], relevant: set[ChunkKey]
) -> float:
    """1/rank of the first relevant chunk, or 0 when none is retrieved."""
    for rank, key in enumerate(ranked, start=1):
        if key in relevant:
            return 1.0 / rank
    return 0.0


def evaluate_ranking(
    ranked: list[ChunkKey], relevant: set[ChunkKey], k: int
) -> dict[str, float]:
    """Per-question retrieval metrics for one ranked chunk list."""
    return {
        f"hit@{k}": 1.0 if hit_at_k(ranked, relevant, k) else 0.0,
        f"recall@{k}": recall_at_k(ranked, relevant, k),
        "mrr": reciprocal_rank(ranked, relevant),
    }


def summarize(results: list[dict[str, float]]) -> dict[str, float]:
    """Mean of each metric over a list of per-question results."""
    if not results:
        return {}
    keys = results[0].keys()
    return {key: sum(item[key] for item in results) / len(results) for key in keys}
