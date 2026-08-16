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


def test_window_bbox_follows_the_window_not_the_whole_page():
    pages = [
        ParsedPage(
            1,
            612,
            792,
            [
                ParsedBlock("alpha " * 50, "text", BBox(10, 20, 80, 16), None),
                ParsedBlock("beta " * 50, "text", BBox(10, 700, 80, 16), None),
            ],
        ),
    ]
    drafts = chunk_pages(pages, target_tokens=50, overlap_tokens=0)
    assert len(drafts) >= 2
    assert drafts[0].bbox is not None
    assert drafts[-1].bbox is not None
    assert drafts[0].bbox.y < 50
    assert drafts[-1].bbox.y > 600
