from app.services.citations import parse_markers


def test_parse_markers_extracts_unique_ordered():
    assert parse_markers("See [2] and [1] then [2].") == [2, 1]
