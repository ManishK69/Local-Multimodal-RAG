from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT / ".env", ".env"),
        extra="ignore",
    )

    postgres_url: str
    redis_url: str
    ollama_host: str = "http://127.0.0.1:11434"
    data_dir: str = "./data"
    max_upload_bytes: int = 52_428_800
    embed_model: str = "nomic-embed-text"
    vision_model: str = "qwen2.5vl:7b"
    generate_model: str = "qwen2.5:7b"
    embedding_dim: int = 768


settings = Settings()
