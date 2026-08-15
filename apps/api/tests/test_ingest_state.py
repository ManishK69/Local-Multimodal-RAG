from app.jobs.ingest import next_status


def test_next_status_order():
    assert next_status("queued") == "parsing"
    assert next_status("parsing") == "captioning"
    assert next_status("captioning") == "chunking"
    assert next_status("chunking") == "embedding"
    assert next_status("embedding") == "ready"
