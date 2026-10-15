"""Application configuration.

All tunables live here and are sourced from environment variables (optionally a
``.env`` file at the project root). Nothing in this module reads secrets from
disk on import beyond that, and no secret is ever echoed back to a client.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import List, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> project root is three parents up from `app`.
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Runtime configuration for the RAG backend."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- Application -------------------------------------------------
    app_name: str = "RAG Document Intelligence"
    api_prefix: str = "/api/v1"
    debug: bool = False

    # ---- Storage -----------------------------------------------------
    # Everything the app writes lives under this directory (configurable).
    data_dir: Path = Field(default=PROJECT_ROOT / "backend" / "data")

    # ---- Uploads / safety limits ------------------------------------
    max_upload_mb: int = 25
    max_pages: int = 400
    max_extracted_chars: int = 4_000_000
    max_chunks_per_document: int = 5_000
    allowed_extensions: List[str] = Field(default_factory=lambda: [".pdf", ".txt", ".docx"])

    # ---- Chunking ----------------------------------------------------
    chunk_size: int = 900          # characters per chunk
    chunk_overlap: int = 150       # characters of overlap between neighbours

    # ---- Embeddings --------------------------------------------------
    # "hashing"         -> deterministic local hashing embeddings (default, no download)
    # "sentence"        -> sentence-transformers neural model (optional install)
    embedding_provider: Literal["hashing", "sentence"] = "hashing"
    embedding_dim: int = 512
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # ---- Retrieval ---------------------------------------------------
    top_k: int = 5
    # Weight of the dense score vs. the BM25 lexical score during fusion.
    dense_weight: float = 0.65
    lexical_weight: float = 0.35
    # Primary fused-score floor: below this the API returns an explicit
    # "insufficient evidence" response instead of guessing. This is the knob exposed
    # on the Settings screen; it is deliberately conservative on its own because the
    # fused scale depends on corpus size and the embedder. A second, structural
    # support rule (see app/services/qa.py) rejects passages with neither keyword
    # overlap nor vector similarity -- measured probes are documented there.
    min_relevance: float = 0.05

    # ---- Answer generation -------------------------------------------
    # "extractive"      -> local, evidence-only, no API key (default)
    # "openai_compatible" -> optional external provider
    answer_provider: Literal["extractive", "openai_compatible"] = "extractive"
    answer_max_sentences: int = 6
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    # ---- CORS --------------------------------------------------------
    cors_origins: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:4173",
            "http://127.0.0.1:4173",
        ]
    )

    # ---- Derived paths ----------------------------------------------
    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def index_dir(self) -> Path:
        return self.data_dir / "indexes"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "metadata.sqlite3"

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.upload_dir, self.index_dir):
            path.mkdir(parents=True, exist_ok=True)

    # ---- Validators --------------------------------------------------
    @field_validator("cors_origins", "allowed_extensions", mode="before")
    @classmethod
    def _split_csv(cls, value):
        """Allow comma-separated strings from env vars."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("allowed_extensions")
    @classmethod
    def _normalise_extensions(cls, value: List[str]) -> List[str]:
        return [ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in value]

    @field_validator("chunk_overlap")
    @classmethod
    def _overlap_smaller_than_size(cls, value: int, info) -> int:
        size = info.data.get("chunk_size", 900)
        if value >= size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    settings = Settings()
    settings.ensure_dirs()
    return settings


def reload_settings() -> Settings:
    """Drop the cache and re-read configuration (used by the settings API)."""
    get_settings.cache_clear()
    return get_settings()


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
