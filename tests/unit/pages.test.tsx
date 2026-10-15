import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { AppProvider } from "@/context/AppContext";
import { WelcomePage } from "@/pages/WelcomePage";
import { ApiError } from "@/services/client";
import type { ApiSurface } from "@/services/api";
import type { DocumentSummary, HealthResponse } from "@/types/api";

const HEALTH: HealthResponse = {
  status: "ok",
  app_name: "RAG Document Intelligence",
  version: "1.0.0",
  embedding_provider: "hashing-subword-v1",
  embedding_dim: 512,
  answer_provider: "extractive",
  generative_available: false,
  documents_indexed: 2,
  data_dir: "/tmp/rag-data",
  uptime_seconds: 7500,
};

function makeSurface(overrides: Partial<ApiSurface> = {}): ApiSurface {
  return {
    health: async () => HEALTH,
    listDocuments: async () => [] as DocumentSummary[],
    ...overrides,
  } as unknown as ApiSurface;
}

function renderWelcome(surface: ApiSurface) {
  return render(
    <MemoryRouter>
      <AppProvider apiSurface={surface}>
        <WelcomePage />
      </AppProvider>
    </MemoryRouter>,
  );
}

describe("WelcomePage", () => {
  it("renders the live health facts returned by the API", async () => {
    renderWelcome(makeSurface());

    expect(await screen.findByText(/systems ready/i)).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getAllByText(/hashing-subword-v1/).length).toBeGreaterThan(0),
    );
    expect(screen.getByText("/tmp/rag-data")).toBeInTheDocument();
    expect(screen.getByText(/2h 5m/)).toBeInTheDocument();
  });

  it("counts documents and distinguishes ready ones", async () => {
    const documents: DocumentSummary[] = [
      {
        id: "a",
        filename: "a.pdf",
        extension: "pdf",
        size_bytes: 1024,
        status: "ready",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
        page_count: 1,
        chunk_count: 4,
        char_count: 100,
        error: null,
      },
      {
        id: "b",
        filename: "b.pdf",
        extension: "pdf",
        size_bytes: 1024,
        status: "processing",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
        page_count: null,
        chunk_count: 0,
        char_count: 0,
        error: null,
      },
    ];

    renderWelcome(makeSurface({ listDocuments: async () => documents }));

    expect(await screen.findByText("1 / 2")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("2.0 KB")).toBeInTheDocument();
  });

  it("shows the real failure when the backend is unreachable", async () => {
    const surface = makeSurface({
      health: async () => {
        throw new ApiError("Could not reach the backend at http://127.0.0.1:8000. Is it running?", {
          code: "network_error",
          status: 0,
        });
      },
    });

    renderWelcome(surface);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/backend is not reachable/i);
    expect(alert).toHaveTextContent(/network_error/);
    expect(screen.getByText(/uvicorn app.main:app/)).toBeInTheDocument();
  });

  it("never fabricates metrics when the document list fails", async () => {
    const listDocuments = vi.fn(async () => {
      throw new ApiError("Database locked", { code: "internal_error", status: 500 });
    });

    renderWelcome(makeSurface({ listDocuments }));

    expect(await screen.findByText(/could not list documents/i)).toBeInTheDocument();
    expect(screen.getByText("Database locked")).toBeInTheDocument();
  });
});
