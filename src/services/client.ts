/**
 * Low-level HTTP client.
 *
 * Every failure the UI can encounter is normalised into an `ApiError` carrying a
 * machine-readable code, a human message and the HTTP status, so components can
 * render the real reason a request failed instead of a generic "something went
 * wrong". Nothing here invents a successful response.
 */

import type { ApiErrorEnvelope } from "@/types/api";

export const DEFAULT_TIMEOUT_MS = 60_000;
export const UPLOAD_TIMEOUT_MS = 180_000;

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details: Record<string, unknown>;
  readonly retryable: boolean;

  constructor(
    message: string,
    options: {
      code?: string;
      status?: number;
      details?: Record<string, unknown>;
      retryable?: boolean;
    } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.code = options.code ?? "unknown_error";
    this.status = options.status ?? 0;
    this.details = options.details ?? {};
    // 0 means "never reached the server" (offline, DNS, CORS, timeout).
    this.retryable =
      options.retryable ??
      (this.status === 0 || this.status === 408 || this.status === 429 || this.status >= 500);
  }
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE" | "OPTIONS";
  body?: unknown;
  /** For multipart uploads; when set, `body` is ignored. */
  formData?: FormData;
  signal?: AbortSignal;
  timeoutMs?: number;
}

export interface ApiClientOptions {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
}

export interface ApiClient {
  readonly baseUrl: string;
  request<T>(path: string, options?: RequestOptions): Promise<T>;
}

function isErrorEnvelope(value: unknown): value is ApiErrorEnvelope {
  if (typeof value !== "object" || value === null) return false;
  const envelope = value as Record<string, unknown>;
  const error = envelope["error"];
  return typeof error === "object" && error !== null && "message" in (error as object);
}

export function createApiClient(options: ApiClientOptions = {}): ApiClient {
  const baseUrl = (options.baseUrl ?? "").replace(/\/+$/, "");
  const doFetch = options.fetchImpl ?? globalThis.fetch.bind(globalThis);

  async function request<T>(path: string, requestOptions: RequestOptions = {}): Promise<T> {
    const {
      method = "GET",
      body,
      formData,
      signal,
      timeoutMs = DEFAULT_TIMEOUT_MS,
    } = requestOptions;

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);

    // Chain an externally supplied signal (e.g. component unmount) to our timeout.
    const onExternalAbort = () => controller.abort();
    signal?.addEventListener("abort", onExternalAbort);

    const headers: Record<string, string> = { Accept: "application/json" };
    let payload: BodyInit | undefined;
    if (formData) {
      payload = formData; // let the browser set the multipart boundary
    } else if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(body);
    }

    let response: Response;
    try {
      response = await doFetch(`${baseUrl}${path}`, {
        method,
        headers,
        body: payload,
        signal: controller.signal,
      });
    } catch (error) {
      const aborted = controller.signal.aborted;
      const wasExternal = Boolean(signal?.aborted);
      if (wasExternal) {
        throw new ApiError("The request was cancelled.", { code: "cancelled", status: 0 });
      }
      if (aborted) {
        throw new ApiError(
          `The request to ${path} timed out after ${Math.round(timeoutMs / 1000)}s.`,
          { code: "timeout", status: 408, retryable: true },
        );
      }
      throw new ApiError(
        `Could not reach the backend at ${baseUrl || window.location.origin}. Is it running?`,
        {
          code: "network_error",
          status: 0,
          retryable: true,
          details: { cause: error instanceof Error ? error.message : String(error) },
        },
      );
    } finally {
      clearTimeout(timeout);
      signal?.removeEventListener("abort", onExternalAbort);
    }

    if (response.status === 204) {
      return undefined as T;
    }

    const raw = await response.text();
    let parsed: unknown = undefined;
    if (raw) {
      try {
        parsed = JSON.parse(raw);
      } catch {
        parsed = undefined;
      }
    }

    if (!response.ok) {
      if (isErrorEnvelope(parsed)) {
        const { code, message, details } = parsed.error;
        throw new ApiError(message || `Request failed with status ${response.status}.`, {
          code: code || "http_error",
          status: response.status,
          details,
        });
      }
      throw new ApiError(
        raw ? raw.slice(0, 300) : `Request failed with status ${response.status}.`,
        { code: "http_error", status: response.status },
      );
    }

    if (parsed === undefined) {
      throw new ApiError("The backend returned a response that was not valid JSON.", {
        code: "invalid_response",
        status: response.status,
      });
    }
    return parsed as T;
  }

  return { baseUrl, request };
}

/** The client the app uses. Empty base URL = same origin (dev proxy / single-host deploy). */
export const apiClient = createApiClient({
  baseUrl: import.meta.env.VITE_API_BASE_URL ?? "",
});
