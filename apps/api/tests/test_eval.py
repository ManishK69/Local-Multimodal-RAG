import json

import pytest
from app.eval.gold import GoldQuestion, load_gold_set
from app.eval.retrieval_metrics import (
    evaluate_ranking,
    hit_at_k,
    recall_at_k,
    reciprocal_rank,
    summarize,
)


def test_hit_at_k():
    ranked = [(1, 0), (1, 1), (2, 0)]
    assert hit_at_k(ranked, {(2, 0)}, 3)
    assert not hit_at_k(ranked, {(2, 0)}, 2)
    assert not hit_at_k(ranked, {(3, 0)}, 3)


def test_recall_at_k_partial():
    ranked = [(1, 0), (1, 1), (2, 0)]
    assert recall_at_k(ranked, {(1, 0), (2, 5)}, 3) == pytest.approx(0.5)


def test_recall_at_k_rejects_empty_relevant():
    with pytest.raises(ValueError, match="non-empty"):
        recall_at_k([(1, 0)], set(), 3)


def test_reciprocal_rank_first_hit_wins():
    ranked = [(1, 0), (2, 3), (2, 4)]
    assert reciprocal_rank(ranked, {(2, 3)}) == pytest.approx(0.5)
    assert reciprocal_rank(ranked, {(9, 9)}) == 0.0


def test_evaluate_ranking_keys_include_k():
    assert evaluate_ranking([(1, 0)], {(1, 0)}, 8) == {
        "hit@8": 1.0,
        "recall@8": 1.0,
        "mrr": 1.0,
    }


def test_summarize_averages():
    assert summarize([{"mrr": 1.0}, {"mrr": 0.5}]) == {"mrr": 0.75}
    assert summarize([]) == {}


def _write_gold(tmp_path, payload):
    path = tmp_path / "gold.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _valid_payload():
    return {
        "name": "test",
        "version": "v1",
        "chunking": {"target_tokens": 400, "overlap_tokens": 80},
        "k": 8,
        "questions": [
            {
                "id": "q1",
                "documentFilename": "sample.pdf",
                "question": "What?",
                "relevantChunks": [{"pageNumber": 1, "chunkIndex": 0}],
                "referenceAnswer": "This.",
                "answerType": "extractive",
                "tags": ["smoke"],
            },
            {
                "id": "q2",
                "documentFilename": "sample.pdf",
                "question": "Who?",
                "relevantChunks": [],
                "referenceAnswer": None,
                "answerType": "unanswerable",
            },
        ],
    }


def test_load_gold_set_ok(tmp_path):
    gold = load_gold_set(_write_gold(tmp_path, _valid_payload()))
    assert gold.name == "test"
    assert gold.k == 8
    assert len(gold.questions) == 2
    first = gold.questions[0]
    assert isinstance(first, GoldQuestion)
    assert first.relevant_keys() == {(1, 0)}
    assert gold.questions[1].answer_type == "unanswerable"


def test_load_gold_set_rejects_duplicate_ids(tmp_path):
    payload = _valid_payload()
    payload["questions"][1]["id"] = "q1"
    with pytest.raises(ValueError, match="duplicate"):
        load_gold_set(_write_gold(tmp_path, payload))


def test_load_gold_set_rejects_unanswerable_with_chunks(tmp_path):
    payload = _valid_payload()
    payload["questions"][1]["relevantChunks"] = [{"pageNumber": 1, "chunkIndex": 0}]
    with pytest.raises(ValueError, match="unanswerable"):
        load_gold_set(_write_gold(tmp_path, payload))


def test_load_gold_set_rejects_missing_reference_answer(tmp_path):
    payload = _valid_payload()
    payload["questions"][0]["referenceAnswer"] = ""
    with pytest.raises(ValueError, match="referenceAnswer"):
        load_gold_set(_write_gold(tmp_path, payload))


def test_load_gold_set_rejects_bad_answer_type(tmp_path):
    payload = _valid_payload()
    payload["questions"][0]["answerType"] = "maybe"
    with pytest.raises(ValueError, match="answerType"):
        load_gold_set(_write_gold(tmp_path, payload))
