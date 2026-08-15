from pathlib import Path

from app.core.config import settings


def pdf_path(sha256: str) -> Path:
    return Path(settings.data_dir) / "files" / f"{sha256}.pdf"


def save_pdf(data: bytes, sha256: str) -> Path:
    path = pdf_path(sha256)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def delete_pdf(sha256: str) -> None:
    pdf_path(sha256).unlink(missing_ok=True)
