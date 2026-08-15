from app.services.rrf import rrf


def test_rrf_prefers_items_high_in_both_lists():
    fused = rrf([[1, 2, 3], [2, 1, 4]], k_rrf=60)
    ids = [i for i, _ in fused]
    assert ids[0] in {1, 2}
    assert set(ids) == {1, 2, 3, 4}


def test_rrf_empty():
    assert rrf([[], []]) == []
