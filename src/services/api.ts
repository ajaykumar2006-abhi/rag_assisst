/**
 * Typed endpoint wrappers. One function per route in `docs/API_CONTRACT.md`.
 * All screen code goes through this module so the contract lives in one place.
 */

import type {
  AnswerResponse,
  ConversationDetail,
  ConversationSummary,
  DocumentDetail,
  DocumentStatusResponse,
  DocumentSummary,
  EvaluationRunList,
  EvaluationRunRequest,
  EvaluationRunResponse,
  EvaluationSummary,
  HealthResponse,
  PrivacyResponse,
  QuestionRequest,
  SettingsResponse,
  SettingsUpdate,
  SettingsUpdateResponse,
  SourceResponse,
  UploadResponse,
} from "@/types/api";
import { apiClient, UPLOAD_TIMEOUT_MS, type ApiClient } from "./client";

export const API_PREFIX = "/api/v1";

export interface ApiSurface {
  health(): Promise<HealthResponse>;
  listDocuments(): Promise<DocumentSummary[]>;
  getDocument(id: string): Promise<DocumentDetail>;
  getDocumentStatus(id: string): Promise<DocumentStatusResponse>;
  getDocumentSources(id: string): Promise<SourceResponse>;
  uploadDocument(file: File): Promise<UploadResponse>;
  deleteDocument(id: string): Promise<{ deleted: string; vectors_removed: number; files_removed: number }>;
  retryDocument(id: string): Promise<UploadResponse>;
  askDocument(id: string, payload: QuestionRequest): Promise<AnswerResponse>;
  askCollection(payload: QuestionRequest): Promise<AnswerResponse>;
  listConversations(): Promise<ConversationSummary[]>;
  createConversation(documentIds: string[], title?: string): Promise<ConversationSummary>;
  getConversation(id: string): Promise<ConversationDetail>;
  deleteConversation(id: string): Promise<{ deleted: string }>;
  clearConversations(): Promise<{ conversations_removed: number }>;
  getSettings(): Promise<SettingsResponse>;
  updateSettings(payload: SettingsUpdate): Promise<SettingsUpdateResponse>;
  getPrivacy(): Promise<PrivacyResponse>;
  deleteAllDocuments(): Promise<{ documents_removed: number; index_size_after: number }>;
  getEvaluationSummary(): Promise<EvaluationSummary>;
  listDatasets(): Promise<string[]>;
  listEvaluationRuns(): Promise<EvaluationRunList>;
  runEvaluation(payload: EvaluationRunRequest): Promise<EvaluationRunResponse>;
}

export function createApiSurface(client: ApiClient = apiClient): ApiSurface {
  const url = (path: string) => `${API_PREFIX}${path}`;

  return {
    health: () => client.request<HealthResponse>(url("/health")),

    listDocuments: () => client.request<DocumentSummary[]>(url("/documents")),
    getDocument: (id) => client.request<DocumentDetail>(url(`/documents/${encodeURIComponent(id)}`)),
    getDocumentStatus: (id) =>
      client.request<DocumentStatusResponse>(url(`/documents/${encodeURIComponent(id)}/status`)),
    getDocumentSources: (id) =>
      client.request<SourceResponse>(url(`/documents/${encodeURIComponent(id)}/sources`)),

    uploadDocument: (file) => {
      const form = new FormData();
      form.append("file", file, file.name);
      return client.request<UploadResponse>(url("/documents"), {
        method: "POST",
        formData: form,
        timeoutMs: UPLOAD_TIMEOUT_MS,
      });
    },

    deleteDocument: (id) =>
      client.request(url(`/documents/${encodeURIComponent(id)}`), { method: "DELETE" }),

    retryDocument: (id) =>
      client.request<UploadResponse>(url(`/documents/${encodeURIComponent(id)}/retry`), {
        method: "POST",
        timeoutMs: UPLOAD_TIMEOUT_MS,
      }),

    askDocument: (id, payload) =>
      client.request<AnswerResponse>(url(`/documents/${encodeURIComponent(id)}/questions`), {
        method: "POST",
        body: payload,
      }),

    askCollection: (payload) =>
      client.request<AnswerResponse>(url("/questions"), { method: "POST", body: payload }),

    listConversations: () => client.request<ConversationSummary[]>(url("/conversations")),
    createConversation: (documentIds, title) =>
      client.request<ConversationSummary>(url("/conversations"), {
        method: "POST",
        body: { document_ids: documentIds, ...(title ? { title } : {}) },
      }),
    getConversation: (id) =>
      client.request<ConversationDetail>(url(`/conversations/${encodeURIComponent(id)}`)),
    deleteConversation: (id) =>
      client.request<{ deleted: string }>(url(`/conversations/${encodeURIComponent(id)}`), {
        method: "DELETE",
      }),
    clearConversations: () =>
      client.request<{ conversations_removed: number }>(url("/conversations"), { method: "DELETE" }),

    getSettings: () => client.request<SettingsResponse>(url("/settings")),
    updateSettings: (payload) =>
      client.request<SettingsUpdateResponse>(url("/settings"), { method: "PATCH", body: payload }),

    getPrivacy: () => client.request<PrivacyResponse>(url("/privacy")),
    deleteAllDocuments: () =>
      client.request<{ documents_removed: number; index_size_after: number }>(
        url("/privacy/documents"),
        { method: "DELETE" },
      ),

    getEvaluationSummary: () => client.request<EvaluationSummary>(url("/evaluation/summary")),
    listDatasets: () => client.request<string[]>(url("/evaluation/datasets")),
    listEvaluationRuns: () => client.request<EvaluationRunList>(url("/evaluation/runs")),
    runEvaluation: (payload) =>
      client.request<EvaluationRunResponse>(url("/evaluation/run"), {
        method: "POST",
        body: payload,
        timeoutMs: 300_000,
      }),
  };
}

export const api = createApiSurface();
