import { describe, expect, it, vi } from "vitest";

import { ApiError, createApiClient } from "@/services/client";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Await a request that is expected to fail and return the thrown error. */
async function capture(promise: Promise<unknown>): Promise<ApiError> {
  let failure: unknown = null;
  try {
    await promise;
  } catch (caught) {
    failure = caught;
  }
  if (failure === null) {
    throw new Error("Expected the request to reject, but it resolved.");
  }
  return failure as ApiError;
}

describe("createApiClient", () => {
  it("parses a successful JSON response", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ status: "ok" })) as unknown as typeof fetch;
    const client = createApiClient({ baseUrl: "http://api.test", fetchImpl });

    await expect(client.request("/health")).resolves.toEqual({ status: "ok" });
    expect(fetchImpl).toHaveBeenCalledWith(
      "http://api.test/health",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("strips a trailing slash from the base URL", () => {
    const client = createApiClient({ baseUrl: "http://api.test/" });
    expect(client.baseUrl).toBe("http://api.test");
  });

  it("surfaces the backend error envelope verbatim", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse({ error: { code: "file_too_large", message: "File exceeds 25 MB.", details: { limit: 25 } } }, 413),
    ) as unknown as typeof fetch;
    const client = createApiClient({ baseUrl: "", fetchImpl });

    const error = await client.request("/documents", { method: "POST" }).catch((caught) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe("file_too_large");
    expect((error as ApiError).message).toBe("File exceeds 25 MB.");
    expect((error as ApiError).status).toBe(413);
    expect((error as ApiError).details).toEqual({ limit: 25 });
    // 4xx errors are the caller's fault: do not offer a blind retry.
    expect((error as ApiError).retryable).toBe(false);
  });

  it("marks 5xx responses as retryable", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse({ error: { code: "internal_error", message: "Boom.", details: {} } }, 500),
    ) as unknown as typeof fetch;
    const client = createApiClient({ baseUrl: "", fetchImpl });

    const error = await capture(client.request("/documents"));
    expect(error).toBeInstanceOf(ApiError);
    expect(error.retryable).toBe(true);
  });

  it("reports a transport failure as a network error", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }) as unknown as typeof fetch;
    const client = createApiClient({ baseUrl: "http://api.test", fetchImpl });

    const error = await capture(client.request("/health"));
    expect(error.code).toBe("network_error");
    expect(error.status).toBe(0);
    expect(error.retryable).toBe(true);
    expect(error.message).toContain("Is it running?");
  });

  it("aborts a request that exceeds its timeout", async () => {
    const fetchImpl = vi.fn(
      (_url: unknown, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            const abort = new Error("aborted");
            abort.name = "AbortError";
            reject(abort);
          });
        }),
    ) as unknown as typeof fetch;
    const client = createApiClient({ baseUrl: "", fetchImpl });

    const error = await capture(client.request("/health", { timeoutMs: 5 }));
    expect(error.code).toBe("timeout");
    expect(error.status).toBe(408);
    expect(error.message).toContain("timed out");
  });

  it("reports a non-JSON body as an invalid response instead of guessing", async () => {
    const fetchImpl = vi.fn(async () => new Response("<html>oops</html>", { status: 200 })) as unknown as typeof fetch;
    const client = createApiClient({ baseUrl: "", fetchImpl });

    const error = await capture(client.request("/health"));
    expect(error.code).toBe("invalid_response");
  });

  it("serialises JSON bodies and sets the content type", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ ok: true })) as unknown as typeof fetch;
    const client = createApiClient({ baseUrl: "", fetchImpl });

    await client.request("/questions", { method: "POST", body: { question: "hello" } });

    const init = (fetchImpl as unknown as { mock: { calls: [string, RequestInit][] } }).mock.calls[0]![1];
    expect(init.method).toBe("POST");
    expect(init.headers).toMatchObject({ "Content-Type": "application/json" });
    expect(init.body).toBe(JSON.stringify({ question: "hello" }));
  });

  it("does not set a content type for multipart uploads", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ ok: true }, 201)) as unknown as typeof fetch;
    const client = createApiClient({ baseUrl: "", fetchImpl });
    const form = new FormData();
    form.append("file", new Blob(["hello"]), "hello.txt");

    await client.request("/documents", { method: "POST", formData: form });

    const init = (fetchImpl as unknown as { mock: { calls: [string, RequestInit][] } }).mock.calls[0]![1];
    expect((init.headers as Record<string, string>)["Content-Type"]).toBeUndefined();
    expect(init.body).toBe(form);
  });

  it("returns undefined for a 204 response", async () => {
    const fetchImpl = vi.fn(async () => new Response(null, { status: 204 })) as unknown as typeof fetch;
    const client = createApiClient({ baseUrl: "", fetchImpl });

    await expect(client.request("/documents/x", { method: "DELETE" })).resolves.toBeUndefined();
  });
});
