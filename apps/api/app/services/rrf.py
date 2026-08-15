from collections import defaultdict


def rrf(
    rank_lists: list[list[int]], k_rrf: int = 60
) -> list[tuple[int, float]]:
    scores: dict[int, float] = defaultdict(float)
    for ranks in rank_lists:
        for rank, item_id in enumerate(ranks, start=1):
            scores[item_id] += 1.0 / (k_rrf + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))
