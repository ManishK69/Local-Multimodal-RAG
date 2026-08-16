from app.services.generate import (
    INSIGHT_TASK,
    build_insight_messages,
    empty_retrieval_answer,
)
from app.services.retrieval import RankedChunk


def test_empty_retrieval_answer_is_explicit():
    message = empty_retrieval_answer()
    assert "searchable" in message.lower()
    assert "I do not know." != message


def test_insight_prompt_asks_for_brief_and_themes():
    chunk = RankedChunk(
        chunk_id=1,
        document_id=2,
        page_number=3,
        content="Paid leave accrues monthly.",
        bbox=None,
        rank=1,
        score=1.0,
        filename="policy.pdf",
    )
    messages = build_insight_messages([chunk])
    user = messages[1]["content"]
    assert "policy.pdf" in user
    assert "Brief" in INSIGHT_TASK
    assert "Themes" in INSIGHT_TASK
    assert "[1]" in user
