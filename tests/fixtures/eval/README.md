# Eval gold sets

`gold.v1.json` is the starter gold question set used by `scripts/eval_rag.py`.
It is deliberately small (5 questions against `tests/fixtures/sample.pdf`) so
the harness runs end to end in seconds. Grow it before trusting any numbers.

## Schema

Top level:

| Field      | Meaning                                                        |
| ---------- | -------------------------------------------------------------- |
| `name`     | Human-readable set name                                        |
| `version`  | Bump when questions or labels change (`v1`, `v2`, …)           |
| `chunking` | Chunker settings the labels were written against               |
| `k`        | Default retrieval depth for the run                            |
| `questions`| The labelled questions                                        |

Each question:

| Field              | Meaning                                                        |
| ------------------ | -------------------------------------------------------------- |
| `id`               | Unique question id                                             |
| `documentFilename` | PDF in `tests/fixtures/` (ingested automatically if needed)    |
| `question`         | The question text                                              |
| `relevantChunks`   | Chunks that answer it: `{pageNumber, chunkIndex}` pairs        |
| `referenceAnswer`  | Gold answer, used later by generation eval                     |
| `answerType`       | `extractive` · `abstractive` · `unanswerable`                   |
| `tags`             | Free-form labels, e.g. `table`, `figure`, `multi-hop`          |

`unanswerable` questions must have empty `relevantChunks` and a null
`referenceAnswer`. They are skipped by retrieval metrics and kept for the
generation eval, where they test whether the model abstains instead of
hallucinating.

## Writing labels

`chunkIndex` is the value in the `chunks.chunk_index` column, which is
deterministic for a fixed chunker configuration. After ingesting a document,
list its chunks:

```sql
SELECT dp.page_number, c.chunk_index, left(c.content, 80)
FROM chunks c
JOIN document_pages dp ON dp.id = c.page_id
JOIN documents d ON d.id = c.document_id
WHERE d.filename = 'mydoc.pdf'
ORDER BY c.chunk_index;
```

If you change the chunker settings, re-ingest and re-label: bump `version`
and record the new `chunking` values in the header so stale labels are
obvious.

## Growing the set

- Aim for 50–100 questions over 5–10 varied PDFs before reporting results.
- Mix `extractive` (answer is a span in one chunk), `abstractive` (needs
  synthesis across chunks), and ~10–15% `unanswerable`.
- Tag questions that need tables or figure captions; slice metrics by tag
  when you have enough of them.
- Split into dev/test once the set is large: tune on dev, report final
  numbers on test.
