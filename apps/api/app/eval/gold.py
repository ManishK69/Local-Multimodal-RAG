from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ANSWER_TYPES = frozenset({"extractive", "abstractive", "unanswerable"})

CHUNKING_KEYS = ("target_tokens", "overlap_tokens")


@dataclass(frozen=True)
class GoldChunkRef:
    """A chunk known to answer a question.

    Addressed by page number and chunk index, matching chunks.chunk_index in
    the database. chunk_index is deterministic for a given chunker
    configuration, which is why the gold set header records the chunking
    settings it was labelled against.
    """

    page_number: int
    chunk_index: int

    def key(self) -> tuple[int, int]:
        return (self.page_number, self.chunk_index)


@dataclass(frozen=True)
class GoldQuestion:
    id: str
    document_filename: str
    question: str
    relevant_chunks: tuple[GoldChunkRef, ...]
    reference_answer: str | None
    answer_type: str
    tags: tuple[str, ...] = ()

    def relevant_keys(self) -> set[tuple[int, int]]:
        return {ref.key() for ref in self.relevant_chunks}


@dataclass(frozen=True)
class GoldSet:
    name: str
    version: str
    chunking: dict[str, int]
    k: int
    questions: tuple[GoldQuestion, ...]


def _error(path: Path, message: str) -> ValueError:
    return ValueError(f"{path}: {message}")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _parse_chunk_ref(path: Path, raw: Any, *, qid: str, index: int) -> GoldChunkRef:
    where = f"question {qid!r} relevantChunks[{index}]"
    if not isinstance(raw, dict):
        raise _error(path, f"{where} must be an object")
    page = raw.get("pageNumber")
    chunk = raw.get("chunkIndex")
    if not _is_int(page) or page < 1:
        raise _error(path, f"{where}.pageNumber must be an integer >= 1")
    if not _is_int(chunk) or chunk < 0:
        raise _error(path, f"{where}.chunkIndex must be an integer >= 0")
    return GoldChunkRef(page_number=page, chunk_index=chunk)


def _parse_question(path: Path, raw: Any, *, seen_ids: set[str]) -> GoldQuestion:
    if not isinstance(raw, dict):
        raise _error(path, "each question must be an object")
    qid = raw.get("id")
    if not isinstance(qid, str) or not qid.strip():
        raise _error(path, "each question needs a non-empty string 'id'")
    if qid in seen_ids:
        raise _error(path, f"duplicate question id {qid!r}")
    seen_ids.add(qid)
    where = f"question {qid!r}"
    filename = raw.get("documentFilename")
    if not isinstance(filename, str) or not filename.strip():
        raise _error(path, f"{where} needs a non-empty 'documentFilename'")
    question = raw.get("question")
    if not isinstance(question, str) or not question.strip():
        raise _error(path, f"{where} needs a non-empty 'question'")
    answer_type = raw.get("answerType")
    if answer_type not in ANSWER_TYPES:
        valid = ", ".join(sorted(ANSWER_TYPES))
        raise _error(path, f"{where} 'answerType' must be one of: {valid}")
    refs_raw = raw.get("relevantChunks", [])
    if not isinstance(refs_raw, list):
        raise _error(path, f"{where} 'relevantChunks' must be a list")
    refs = tuple(
        _parse_chunk_ref(path, item, qid=qid, index=i)
        for i, item in enumerate(refs_raw)
    )
    reference = raw.get("referenceAnswer")
    if reference is not None and not isinstance(reference, str):
        raise _error(path, f"{where} 'referenceAnswer' must be a string or null")
    if answer_type == "unanswerable":
        if refs:
            raise _error(path, f"{where} is unanswerable but lists relevant chunks")
    else:
        if not refs:
            raise _error(path, f"{where} needs at least one relevant chunk")
        if not reference or not reference.strip():
            raise _error(
                path, f"{where} needs a 'referenceAnswer' (used by generation eval)"
            )
    tags_raw = raw.get("tags", [])
    if not isinstance(tags_raw, list) or any(
        not isinstance(tag, str) for tag in tags_raw
    ):
        raise _error(path, f"{where} 'tags' must be a list of strings")
    return GoldQuestion(
        id=qid,
        document_filename=filename,
        question=question,
        relevant_chunks=refs,
        reference_answer=reference,
        answer_type=answer_type,
        tags=tuple(tags_raw),
    )


def load_gold_set(path: str | Path) -> GoldSet:
    """Load and validate a gold question set from JSON.

    Raises ValueError with a precise message when the file is malformed.
    """
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"gold set not found: {path}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise _error(path, "top level must be an object")
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise _error(path, "top level needs a non-empty 'name'")
    version = raw.get("version")
    if not isinstance(version, str) or not version.strip():
        raise _error(path, "top level needs a non-empty 'version'")
    chunking = raw.get("chunking")
    if not isinstance(chunking, dict):
        raise _error(path, "'chunking' must be an object")
    for key in CHUNKING_KEYS:
        value = chunking.get(key)
        if not _is_int(value) or value <= 0:
            raise _error(path, f"'chunking.{key}' must be a positive integer")
    k = raw.get("k")
    if not _is_int(k) or k <= 0:
        raise _error(path, "'k' must be a positive integer")
    questions_raw = raw.get("questions")
    if not isinstance(questions_raw, list) or not questions_raw:
        raise _error(path, "'questions' must be a non-empty list")
    seen_ids: set[str] = set()
    questions = tuple(
        _parse_question(path, item, seen_ids=seen_ids) for item in questions_raw
    )
    return GoldSet(
        name=name,
        version=version,
        chunking={key: chunking[key] for key in CHUNKING_KEYS},
        k=k,
        questions=questions,
    )
