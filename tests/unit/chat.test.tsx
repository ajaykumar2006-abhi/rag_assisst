import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChatTranscript, type TranscriptMessage } from "@/components/ChatTranscript";
import { AppProvider } from "@/context/AppContext";
import { ChatPage } from "@/pages/ChatPage";
import type { ApiSurface } from "@/services/api";
import { ApiError } from "@/services/client";
import type {
  AnswerResponse,
  ConversationSummary,
  DocumentSummary,
  HealthResponse,
  QuestionRequest,
} from "@/types/api";

const HEALTH: HealthResponse = {
  status: "ok",
  app_name: "RAG Document Intelligence",
  version: "1.0.0",
  embedding_provider: "hashing-subword-v1",
  embedding_dim: 512,
  answer_provider: "extractive",
  generative_available: false,
  documents_indexed: 1,
  data_dir: "/tmp/rag-data",
  uptime_seconds: 60,
};

const READY_DOC: DocumentSummary = {
  id: "doc-a",
  filename: "helios_mission_brief.pdf",
  extension: "pdf",
  size_bytes: 4096,
  status: "ready",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  page_count: 3,
  chunk_count: 12,
  char_count: 4096,
  error: null,
};

const CONVERSATION: ConversationSummary = {
  id: "conv-1",
  document_ids: ["doc-a"],
  title: "What altitude?",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  message_count: 0,
};

function makeAnswer(overrides: Partial<AnswerResponse> = {}): AnswerResponse {
  return {
    question: "What altitude does the observatory orbit at?",
    answer: "The observatory orbits at an altitude of 705 km.",
    answer_mode: "extractive",
    insufficient_evidence: false,
    citations: [],
    retrieved_count: 3,
    latency_ms: 12,
    embedding_provider: "hashing-subword-v1",
    conversation_id: "conv-1",
    notice: null,
    ...overrides,
  };
}

function makeSurface(overrides: Partial<ApiSurface> = {}): ApiSurface {
  return {
    health: async () => HEALTH,
    listDocuments: async () => [READY_DOC],
    listConversations: async () => [CONVERSATION],
    createConversation: async () => CONVERSATION,
    getConversation: async () => {
      throw new ApiError("not used in these tests", { code: "not_found", status: 404 });
    },
    askDocument: async () => makeAnswer(),
    askCollection: async () => makeAnswer(),
    clearConversations: async () => ({ conversations_removed: 1 }),
    ...overrides,
  } as unknown as ApiSurface;
}

function renderChat(surface: ApiSurface) {
  return render(
    <MemoryRouter>
      <AppProvider apiSurface={surface}>
        <ChatPage />
      </AppProvider>
    </MemoryRouter>,
  );
}

function askQuestion(text: string) {
  fireEvent.change(screen.getByLabelText(/your question/i), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: /^ask$/i }));
}

function transcriptMessage(overrides: Partial<TranscriptMessage> = {}): TranscriptMessage {
  return {
    id: "a-1",
    role: "assistant",
    content: "The observatory orbits at an altitude of 705 km.",
    createdAt: "2026-01-01T00:00:00Z",
    citations: [],
    answerMode: "extractive",
    ...overrides,
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ChatTranscript — copy answer", () => {
  it("copies the answer text to the clipboard and confirms it", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(window.navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });

    render(
      <ChatTranscript messages={[transcriptMessage()]} onCitationClick={() => {}} />,
    );

    fireEvent.click(screen.getByRole("button", { name: /copy this answer/i }));
    expect(await screen.findByText(/copied/i)).toBeInTheDocument();
    expect(writeText).toHaveBeenCalledWith(
      "The observatory orbits at an altitude of 705 km.",
    );
  });

  it("says Copy failed instead of pretending when the clipboard is unavailable", async () => {
    Object.defineProperty(window.navigator, "clipboard", {
      value: undefined,
      configurable: true,
    });
    const execCommand = vi.fn(() => {
      throw new Error("not supported");
    });
    Object.defineProperty(document, "execCommand", {
      value: execCommand,
      configurable: true,
    });

    render(
      <ChatTranscript messages={[transcriptMessage()]} onCitationClick={() => {}} />,
    );

    fireEvent.click(screen.getByRole("button", { name: /copy this answer/i }));
    expect(await screen.findByText(/copy failed/i)).toBeInTheDocument();
  });

  it("offers retry only for the most recent failed turn", () => {
    const onRetry = vi.fn();
    render(
      <ChatTranscript
        messages={[
          transcriptMessage({ id: "f-1", content: "", error: "first failure" }),
          transcriptMessage({ id: "f-2", content: "", error: "second failure" }),
        ]}
        onCitationClick={() => {}}
        onRetry={onRetry}
        retryableMessageId="f-2"
      />,
    );

    const retryButtons = screen.getAllByRole("button", { name: /try again/i });
    expect(retryButtons).toHaveLength(1);
    fireEvent.click(retryButtons[0]!);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});

describe("ChatPage — question flow controls", () => {
  it("answers a question scoped to the ready document", async () => {
    const askDocument = vi.fn(
      async (_id: string, _payload: QuestionRequest) => makeAnswer(),
    );
    renderChat(makeSurface({ askDocument }));

    await screen.findByLabelText(/your question/i);
    askQuestion("What altitude does the observatory orbit at?");

    expect(
      await screen.findByText(/altitude of 705 km/i),
    ).toBeInTheDocument();
    expect(askDocument).toHaveBeenCalledTimes(1);
    expect(askDocument.mock.calls[0]?.[0]).toBe("doc-a");
  });

  it("starts a new conversation without deleting the stored history", async () => {
    const listConversations = vi.fn(async () => [CONVERSATION]);
    renderChat(makeSurface({ listConversations }));

    await screen.findByLabelText(/your question/i);
    askQuestion("What altitude does the observatory orbit at?");
    await screen.findByText(/altitude of 705 km/i);

    fireEvent.click(screen.getByRole("button", { name: /new conversation/i }));

    // The live transcript is cleared...
    await waitFor(() => {
      expect(screen.queryByText(/altitude of 705 km/i)).not.toBeInTheDocument();
      expect(
        screen.queryByText("What altitude does the observatory orbit at?"),
      ).not.toBeInTheDocument();
    });
    // ...but the saved conversation is still offered for reopening.
    expect(
      await screen.findByRole("button", { name: /what altitude\?/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/nothing asked yet/i)).toBeInTheDocument();
  });

  it("shows the failure, then retries the same question successfully", async () => {
    const askDocument = vi
      .fn<ApiSurface["askDocument"]>()
      .mockRejectedValueOnce(
        new ApiError("The backend did not answer in time.", { code: "timeout", status: 504 }),
      )
      .mockResolvedValueOnce(makeAnswer());
    renderChat(makeSurface({ askDocument }));

    await screen.findByLabelText(/your question/i);
    const question = "What altitude does the observatory orbit at?";
    askQuestion(question);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/this question failed/i);
    expect(alert).toHaveTextContent(/did not answer in time/i);

    fireEvent.click(screen.getByRole("button", { name: /try again/i }));

    expect(await screen.findByText(/altitude of 705 km/i)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    // The failed turn was replaced, not duplicated.
    expect(screen.getAllByText(question)).toHaveLength(1);
    expect(askDocument).toHaveBeenCalledTimes(2);
  });
});
