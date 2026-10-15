"""Pydantic models describing every request and response in the API.

The frontend mirrors these shapes in ``frontend/src/types/api.ts``; keep the two
files in sync (see ``docs/API_CONTRACT.md``).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enumerations -- mirrored verbatim on the frontend.
# ---------------------------------------------------------------------------


class DocumentStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class StageName(str, Enum):
    VALIDATE = "validate"
    EXTRACT = "extract"
    STRUCTURE = "structure"
    CHUNK = "chunk"
    EMBED = "embed"
    INDEX = "index"
    VERIFY = "verify"


class StageState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AnswerMode(str, Enum):
    EXTRACTIVE = "extractive"
    GENERATIVE = "generative"
    INSUFFICIENT = "insufficient"


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


class Stage(BaseModel):
    """One step of the processing pipeline with real backend progress."""

    name: StageName
    label: str
    state: StageState = StageState.PENDING
    detail: str = ""
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    progress: float = Field(default=0.0, ge=0.0, le=1.0)


class DocumentSummary(BaseModel):
    """Compact document view used by list endpoints."""

    id: str
    filename: str
    extension: str
    size_bytes: int
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime
    page_count: Optional[int] = None
    chunk_count: int = 0
    char_count: int = 0
    error: Optional[str] = None


class DocumentDetail(DocumentSummary):
    """Full document view including live pipeline stages."""

    stages: List[Stage] = Field(default_factory=list)
    embedding_provider: str = ""
    embedding_dim: int = 0
    answer_provider: str = ""
    indexed: bool = False


class DocumentStatusResponse(BaseModel):
    """Polled by the Processing Observatory screen."""

    id: str
    status: DocumentStatus
    stages: List[Stage]
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    error: Optional[str] = None
    retryable: bool = False
    indexed: bool = False


class UploadResponse(BaseModel):
    document: DocumentDetail
    message: str


# ---------------------------------------------------------------------------
# Question answering
# ---------------------------------------------------------------------------


class Citation(BaseModel):
    """A verifiable pointer back into an uploaded document."""

    index: int                      # 1-based marker used in the answer text
    document_id: str
    filename: str
    chunk_id: str
    page: Optional[int] = None
    score: float
    dense_score: float = 0.0
    lexical_score: float = 0.0
    excerpt: str
    char_start: int = 0
    char_end: int = 0


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    document_ids: Optional[List[str]] = None
    top_k: Optional[int] = Field(default=None, ge=1, le=50)
    conversation_id: Optional[str] = None


class AnswerResponse(BaseModel):
    question: str
    answer: str
    answer_mode: AnswerMode
    insufficient_evidence: bool = False
    citations: List[Citation] = Field(default_factory=list)
    retrieved_count: int = 0
    latency_ms: float = 0.0
    embedding_provider: str = ""
    conversation_id: Optional[str] = None
    notice: Optional[str] = None


class SourceResponse(BaseModel):
    document_id: str
    filename: str
    sources: List[Citation]


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------


class ConversationMessage(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime
    citations: List[Citation] = Field(default_factory=list)
    answer_mode: Optional[AnswerMode] = None


class ConversationSummary(BaseModel):
    id: str
    document_ids: List[str]
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ConversationDetail(ConversationSummary):
    messages: List[ConversationMessage] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Health / settings
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str
    app_name: str
    version: str
    embedding_provider: str
    embedding_dim: int
    answer_provider: str
    generative_available: bool
    documents_indexed: int
    data_dir: str
    uptime_seconds: float


class SettingsResponse(BaseModel):
    """Public, non-secret view of configuration."""

    chunk_size: int
    chunk_overlap: int
    top_k: int
    dense_weight: float
    lexical_weight: float
    min_relevance: float
    max_upload_mb: int
    max_pages: int
    embedding_provider: str
    embedding_model: str
    embedding_dim: int
    answer_provider: str
    answer_max_sentences: int
    # True only when an external generation provider's API key is actually set.
    llm_configured: bool
    llm_base_url: str
    llm_model: str
    # Whether the configured answerer can run right now, plus why not if it cannot.
    # The local extractive answerer is always available and needs no key.
    answerer_available: bool
    answerer_reason: str
    cors_origins: List[str]
    allowed_extensions: List[str]
    data_dir: str
    runs_locally: List[str]
    requires_external_service: List[str]


class SettingsUpdate(BaseModel):
    chunk_size: Optional[int] = Field(default=None, ge=200, le=4000)
    chunk_overlap: Optional[int] = Field(default=None, ge=0, le=1000)
    top_k: Optional[int] = Field(default=None, ge=1, le=50)
    dense_weight: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    lexical_weight: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    min_relevance: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    answer_max_sentences: Optional[int] = Field(default=None, ge=1, le=20)
    embedding_provider: Optional[str] = None
    answer_provider: Optional[str] = None


class SettingsUpdateResponse(BaseModel):
    settings: SettingsResponse
    applied: bool
    notice: Optional[str] = None


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


class EvaluationCaseResult(BaseModel):
    id: str
    question: str
    expected_answer: str
    retrieved_chunk_ids: List[str]
    relevant_chunk_ids: List[str]
    recall_at_k: float
    precision_at_k: float
    reciprocal_rank: float
    citation_hit: bool
    answered: bool
    answer_mode: AnswerMode
    latency_ms: float


class EvaluationRunRequest(BaseModel):
    dataset: Optional[str] = None           # name of a bundled dataset, or None for synthetic
    top_k: Optional[int] = Field(default=None, ge=1, le=20)
    limit: Optional[int] = Field(default=None, ge=1, le=200)


class EvaluationSummary(BaseModel):
    documents_total: int
    documents_ready: int
    documents_failed: int
    chunks_indexed: int
    questions_answered: int
    errors_total: int
    mean_answer_latency_ms: float
    p95_answer_latency_ms: float
    embedding_provider: str
    answer_provider: str


class EvaluationRunResponse(BaseModel):
    run_id: str
    dataset: str
    created_at: datetime
    sample_count: int
    top_k: int
    recall_at_k: float
    precision_at_k: float
    mrr: float
    citation_hit_rate: float
    answer_rate: float
    mean_latency_ms: float
    cases: List[EvaluationCaseResult]
    methodology: str
    limitations: List[str]
    result_path: Optional[str] = None


class EvaluationRunList(BaseModel):
    runs: List[Dict[str, Any]] = Field(default_factory=list)
