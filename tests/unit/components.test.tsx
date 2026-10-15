import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DocumentDropzone } from "@/components/DocumentDropzone";
import { DocumentTable } from "@/components/DocumentTable";
import { Nova } from "@/components/Nova";
import { CitationCard } from "@/components/CitationCard";
import { StageTimeline } from "@/components/ui/StageTimeline";
import { ToastStack } from "@/components/ui/ToastStack";
import type { Citation, DocumentSummary, Stage } from "@/types/api";

function makeDocument(overrides: Partial<DocumentSummary> = {}): DocumentSummary {
  return {
    id: "doc-1",
    filename: "orbit.pdf",
    extension: "pdf",
    size_bytes: 2048,
    status: "ready",
    created_at: "2026-01-02T03:04:05Z",
    updated_at: "2026-01-02T03:05:00Z",
    page_count: 3,
    chunk_count: 12,
    char_count: 4096,
    error: null,
    ...overrides,
  };
}

function makeCitation(overrides: Partial<Citation> = {}): Citation {
  return {
    index: 1,
    document_id: "doc-1",
    filename: "orbit.pdf",
    chunk_id: "doc-1::0000",
    page: 2,
    score: 0.77,
    dense_score: 0.81,
    lexical_score: 0.4,
    excerpt: "The spacecraft completed three orbits.",
    char_start: 120,
    char_end: 400,
    ...overrides,
  };
}

describe("Nova", () => {
  it("announces her mood and renders her message as real text", () => {
    render(<Nova mood="thinking" message="Reading your documents…" />);

    expect(screen.getByRole("group", { name: /thinking/i })).toBeInTheDocument();
    expect(screen.getByText("Reading your documents…")).toBeInTheDocument();
  });

  it("omits the bubble entirely when there is no message", () => {
    const { container } = render(<Nova mood="idle" />);
    expect(container.querySelector(".nova__bubble")).toBeNull();
  });

  it("hides the drawing from assistive technology", () => {
    const { container } = render(<Nova mood="happy" />);
    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });
});

describe("DocumentDropzone", () => {
  it("accepts supported files and reports them upward", () => {
    const onFiles = vi.fn();
    render(<DocumentDropzone onFiles={onFiles} allowedExtensions={["pdf", "txt"]} maxBytes={1024 * 1024} />);

    const input = screen.getByTestId("file-input") as HTMLInputElement;
    const file = new File(["hello"], "notes.txt", { type: "text/plain" });
    fireEvent.change(input, { target: { files: [file] } });

    expect(onFiles).toHaveBeenCalledWith([file]);
    expect(screen.queryByText(/were not added/i)).toBeNull();
  });

  it("rejects an unsupported extension with a specific reason", () => {
    const onFiles = vi.fn();
    render(<DocumentDropzone onFiles={onFiles} allowedExtensions={["pdf"]} maxBytes={1024 * 1024} />);

    fireEvent.change(screen.getByTestId("file-input"), {
      target: { files: [new File(["x"], "photo.png", { type: "image/png" })] },
    });

    expect(onFiles).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("photo.png");
    expect(screen.getByRole("alert")).toHaveTextContent("Unsupported type");
  });

  it("rejects a file larger than the configured limit", () => {
    const onFiles = vi.fn();
    render(<DocumentDropzone onFiles={onFiles} allowedExtensions={["pdf"]} maxBytes={4} />);

    fireEvent.change(screen.getByTestId("file-input"), {
      target: { files: [new File([new Uint8Array(64)], "huge.pdf")] },
    });

    expect(onFiles).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("Too large");
  });

  it("accepts the valid files and reports the invalid one in the same batch", () => {
    const onFiles = vi.fn();
    render(<DocumentDropzone onFiles={onFiles} allowedExtensions={["pdf"]} maxBytes={1024 * 1024} />);

    const good = new File(["good"], "report.pdf");
    fireEvent.change(screen.getByTestId("file-input"), {
      target: { files: [good, new File(["bad"], "notes.txt")] },
    });

    expect(onFiles).toHaveBeenCalledWith([good]);
    expect(screen.getByRole("alert")).toHaveTextContent("notes.txt");
  });
});

describe("DocumentTable", () => {
  it("sorts newest first by default and renders document facts", () => {
    const documents = [
      makeDocument({ id: "old", filename: "old.pdf", created_at: "2026-01-01T00:00:00Z" }),
      makeDocument({ id: "new", filename: "new.pdf", created_at: "2026-02-01T00:00:00Z" }),
    ];
    render(
      <DocumentTable
        documents={documents}
        selectedIds={[]}
        onToggleSelected={() => undefined}
        onToggleAll={() => undefined}
        onAsk={() => undefined}
        onInspect={() => undefined}
        onDelete={() => undefined}
      />,
    );

    const rows = screen.getAllByRole("row").slice(1); // drop the header row
    expect(within(rows[0]!).getByText("new.pdf")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("old.pdf")).toBeInTheDocument();
    expect(within(rows[0]!).getByText("2.0 KB")).toBeInTheDocument();
    expect(within(rows[0]!).getByText("12")).toBeInTheDocument();
  });

  it("names each action after its document for screen readers", () => {
    render(
      <DocumentTable
        documents={[makeDocument({ filename: "orbit.pdf" })]}
        selectedIds={[]}
        onToggleSelected={() => undefined}
        onToggleAll={() => undefined}
        onAsk={() => undefined}
        onInspect={() => undefined}
        onDelete={() => undefined}
      />,
    );

    expect(screen.getByRole("button", { name: /delete orbit.pdf/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /ask questions about orbit.pdf/i })).toBeInTheDocument();
  });

  it("passes the whole document to onDelete", () => {
    const onDelete = vi.fn();
    const document = makeDocument();
    render(
      <DocumentTable
        documents={[document]}
        selectedIds={[]}
        onToggleSelected={() => undefined}
        onToggleAll={() => undefined}
        onAsk={() => undefined}
        onInspect={() => undefined}
        onDelete={onDelete}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /delete orbit.pdf/i }));
    expect(onDelete).toHaveBeenCalledWith(document);
  });

  it("disables Ask until the document is ready", () => {
    render(
      <DocumentTable
        documents={[makeDocument({ status: "processing" })]}
        selectedIds={[]}
        onToggleSelected={() => undefined}
        onToggleAll={() => undefined}
        onAsk={() => undefined}
        onInspect={() => undefined}
        onDelete={() => undefined}
      />,
    );

    expect(screen.getByRole("button", { name: /ask questions about orbit.pdf/i })).toBeDisabled();
  });

  it("shows an empty state instead of an empty table", () => {
    render(
      <DocumentTable
        documents={[]}
        selectedIds={[]}
        onToggleSelected={() => undefined}
        onToggleAll={() => undefined}
        onAsk={() => undefined}
        onInspect={() => undefined}
        onDelete={() => undefined}
      />,
    );

    expect(screen.getByText(/no documents yet/i)).toBeInTheDocument();
  });

  it("selects every document when the header checkbox is used", () => {
    const onToggleAll = vi.fn();
    const documents = [makeDocument({ id: "a" }), makeDocument({ id: "b" })];
    render(
      <DocumentTable
        documents={documents}
        selectedIds={[]}
        onToggleSelected={() => undefined}
        onToggleAll={onToggleAll}
        onAsk={() => undefined}
        onInspect={() => undefined}
        onDelete={() => undefined}
      />,
    );

    fireEvent.click(screen.getByLabelText(/select all documents/i));
    expect(onToggleAll).toHaveBeenCalledWith(["a", "b"]);
  });
});

describe("StageTimeline", () => {
  it("renders real stage names, states and completed durations", () => {
    const stages: Stage[] = [
      {
        name: "extract",
        label: "Extract text",
        state: "completed",
        detail: "34 pages, 12,004 characters",
        progress: 1,
        started_at: "2026-01-01T00:00:00Z",
        finished_at: "2026-01-01T00:00:01.500Z",
      },
      {
        name: "embed",
        label: "Embed chunks",
        state: "running",
        detail: "embedding 12 of 40 chunks",
        progress: 0.3,
        started_at: "2026-01-01T00:00:02Z",
        finished_at: null,
      },
    ];

    render(<StageTimeline stages={stages} />);

    expect(screen.getByText(/1\. Extract text/)).toBeInTheDocument();
    expect(screen.getByText("34 pages, 12,004 characters")).toBeInTheDocument();
    expect(screen.getByText("1.50 s")).toBeInTheDocument();
    expect(screen.getByText(/embedding 12 of 40 chunks/)).toBeInTheDocument();
  });

  it("says so when no stages have been reported", () => {
    render(<StageTimeline stages={[]} />);
    expect(screen.getByText(/no pipeline stages reported yet/i)).toBeInTheDocument();
  });
});

describe("CitationCard", () => {
  it("shows the verbatim excerpt, page and score breakdown", () => {
    render(<CitationCard citation={makeCitation()} />);

    expect(screen.getByText("The spacecraft completed three orbits.")).toBeInTheDocument();
    expect(screen.getByText(/page 2/)).toBeInTheDocument();
    expect(screen.getByText(/vector 0.8100/)).toBeInTheDocument();
  });

  it("states when the page is unknown rather than guessing", () => {
    render(<CitationCard citation={makeCitation({ page: null })} />);
    expect(screen.getByText(/page not available/)).toBeInTheDocument();
  });
});

describe("ToastStack", () => {
  it("announces errors assertively and offers retry", () => {
    const dismiss = vi.fn();
    const retry = vi.fn();
    render(
      <ToastStack
        toasts={[{ id: "t1", tone: "error", title: "Upload failed", message: "Network unreachable", retry }]}
        onDismiss={dismiss}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Upload failed");
    fireEvent.click(screen.getByRole("button", { name: /^retry$/i }));
    expect(retry).toHaveBeenCalled();
    expect(dismiss).toHaveBeenCalledWith("t1");
  });

  it("renders nothing when there are no toasts", () => {
    const { container } = render(<ToastStack toasts={[]} onDismiss={() => undefined} />);
    expect(container).toBeEmptyDOMElement();
  });
});
