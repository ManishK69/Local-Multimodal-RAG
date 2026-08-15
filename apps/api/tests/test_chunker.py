from app.services.chunker import BBox, ParsedBlock, ParsedPage, chunk_pages


def test_chunker_does_not_merge_pages():
    pages = [
        ParsedPage(
            1, 612, 792,
            [ParsedBlock("alpha "*50, "text", BBox(0, 0, 100, 20), None)],
        ),
        ParsedPage(
            2, 612, 792,
            [ParsedBlock("beta "*50, "text", BBox(0, 0, 100, 20), None)],
        ),
    ]
    drafts = chunk_pages(pages, target_tokens=400, overlap_tokens=80)
    assert {d.page_number for d in drafts} == {1, 2}
    assert [d.chunk_index for d in drafts] == list(range(len(drafts)))
