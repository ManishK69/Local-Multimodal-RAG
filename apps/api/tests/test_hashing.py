from pathlib import Path

from app.services.hashing import sha256_bytes, sha256_file


def test_sha256_bytes_stable():
    assert sha256_bytes(b"abc") == sha256_bytes(b"abc")
    assert len(sha256_bytes(b"abc")) == 64
    assert sha256_bytes(b"abc") != sha256_bytes(b"abd")


def test_sha256_file_matches_bytes(tmp_path: Path):
    path = tmp_path / "doc.bin"
    path.write_bytes(b"abc")
    assert sha256_file(path) == sha256_bytes(b"abc")
