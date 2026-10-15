/**
 * Typed mirror of the backend contract in `backend/app/schemas/models.py`.
 * Kept in sync by hand; `docs/API_CONTRACT.md` lists the same shapes.
 */

export type DocumentStatus = "queued" | "processing" | "ready" | "failed";

export type StageName =
  | "validate"
  | "extract"
  | "structure"
  | "chunk"
  | "embed"
  | "index"
  | "verify";

export type StageState = "pending" | "running" | "completed" | "failed";

export type AnswerMode = "extractive" | "generative" | "insufficient";

export interface Stage {
  name: StageName;
  label: string;
  state: StageState;
  detail: string;
  started_at: string | null;
  finished_at: string | null;
  progress: number;
}

export interface DocumentSummary {
  id: string;
  filename: string;
  extension: string;
  size_bytes: number;
  status: DocumentStatus;
  created_at: string;
  updated_at: string;
  page_count: number | null;
  chunk_count: number;
  char_count: number;
  error: string | null;
}

export interface DocumentDetail extends DocumentSummary {
  stages: Stage[];
  embedding_provider: string;
  embedding_dim: number;
  answer_provider: string;
  indexed: boolean;
}

export interface DocumentStatusResponse {
  id: string;
  status: DocumentStatus;
  stages: Stage[];
  progress: number;
  error: string | null;
  retryable: boolean;
  indexed: boolean;
}

export interface UploadResponse {
  document: DocumentDetail;
  message: string;
}

export interface Citation {
  index: number;
  document_id: string;
  filename: string;
  chunk_id: string;
  page: number | null;
  score: number;
  dense_score: number;
  lexical_score: number;
  excerpt: string;
  char_start: number;
  char_end: number;
}

export interface QuestionRequest {
  question: string;
  document_ids?: string[] | null;
  top_k?: number | null;
  conversation_id?: string | null;
}

export interface AnswerResponse {
  question: string;
  answer: string;
  answer_mode: AnswerMode;
  insufficient_evidence: boolean;
  citations: Citation[];
  retrieved_count: number;
  latency_ms: number;
  embedding_provider: string;
  conversation_id: string | null;
  notice: string | null;
}

export interface SourceResponse {
  document_id: string;
  filename: string;
  sources: Citation[];
}

export interface HealthResponse {
  status: string;
  app_name: string;
  version: string;
  embedding_provider: string;
  embedding_dim: number;
  answer_provider: string;
  generative_available: boolean;
  documents_indexed: number;
  data_dir: string;
  uptime_seconds: number;
}

export interface ConversationSummary {
  id: string;
  document_ids: string[];
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ConversationMessage {
  id: string;
  role: "user" | "assistant" | string;
  content: string;
  created_at: string;
  citations: Citation[];
  answer_mode: AnswerMode | null;
}

export interface ConversationDetail extends ConversationSummary {
  messages: ConversationMessage[];
}

export interface SettingsResponse {
  chunk_size: number;
  chunk_overlap: number;
  top_k: number;
  dense_weight: number;
  lexical_weight: number;
  min_relevance: number;
  max_upload_mb: number;
  max_pages: number;
  embedding_provider: string;
  embedding_model: string;
  embedding_dim: number;
  answer_provider: string;
  answer_max_sentences: number;
  llm_configured: boolean;
  llm_base_url: string;
  llm_model: string;
  answerer_available: boolean;
  answerer_reason: string;
  cors_origins: string[];
  allowed_extensions: string[];
  data_dir: string;
  runs_locally: string[];
  requires_external_service: string[];
}

export interface SettingsUpdate {
  chunk_size?: number;
  chunk_overlap?: number;
  top_k?: number;
  dense_weight?: number;
  lexical_weight?: number;
  min_relevance?: number;
  answer_max_sentences?: number;
  embedding_provider?: string;
  answer_provider?: string;
}

export interface SettingsUpdateResponse {
  settings: SettingsResponse;
  applied: boolean;
  notice: string | null;
}

export interface EvaluationCaseResult {
  id: string;
  question: string;
  expected_answer: string;
  retrieved_chunk_ids: string[];
  relevant_chunk_ids: string[];
  recall_at_k: number;
  precision_at_k: number;
  reciprocal_rank: number;
  citation_hit: boolean;
  answered: boolean;
  answer_mode: AnswerMode;
  latency_ms: number;
}

export interface EvaluationSummary {
  documents_total: number;
  documents_ready: number;
  documents_failed: number;
  chunks_indexed: number;
  questions_answered: number;
  errors_total: number;
  mean_answer_latency_ms: number;
  p95_answer_latency_ms: number;
  embedding_provider: string;
  answer_provider: string;
}

export interface EvaluationRunRequest {
  dataset?: string | null;
  top_k?: number | null;
  limit?: number | null;
}

export interface EvaluationRunResponse {
  run_id: string;
  dataset: string;
  created_at: string;
  sample_count: number;
  top_k: number;
  recall_at_k: number;
  precision_at_k: number;
  mrr: number;
  citation_hit_rate: number;
  answer_rate: number;
  mean_latency_ms: number;
  cases: EvaluationCaseResult[];
  methodology: string;
  limitations: string[];
  result_path: string | null;
}

export interface EvaluationRunRecord {
  run_id: string;
  dataset: string;
  created_at: string;
  sample_count: number;
  top_k: number;
  metrics: Record<string, number>;
  result_path: string | null;
}

export interface EvaluationRunList {
  runs: EvaluationRunRecord[];
}

export interface PrivacyStorageEntry {
  what: string;
  where: string;
  count: number;
  bytes: number;
}

export interface PrivacyResponse {
  data_dir: string;
  storage: PrivacyStorageEntry[];
  retention: string;
  external_services: string;
  delete_instructions: string[];
}

/** Shape of every error the API returns. */
export interface ApiErrorEnvelope {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
  };
}
