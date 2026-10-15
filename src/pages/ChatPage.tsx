import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { ChatTranscript, type TranscriptMessage } from "@/components/ChatTranscript";
import { Nova } from "@/components/Nova";
import { SourceViewer } from "@/components/SourceViewer";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { ErrorState, Notice } from "@/components/ui/Feedback";
import { NumberField, TextAreaField } from "@/components/ui/Field";
import { useApp } from "@/context/AppContext";
import { usePolling } from "@/hooks/usePolling";
import { formatRelative } from "@/services/format";
import { resolveSearchScope } from "@/services/scope";
import { ApiError } from "@/services/client";
import type { Citation, ConversationSummary, DocumentSummary } from "@/types/api";

const SAMPLE_QUESTIONS = [
  "What is the main topic of this document?",
  "Summarise the key steps described.",
  "Which numbers or figures are mentioned?",
];

/**
 * Screen 4 — grounded question answering.
 *
 * The question is only ever answered from retrieved passages of the selected
 * documents. Answers carry citation markers that open the exact source, the
 * answer mode is always labelled (extractive vs. generated vs. insufficient
 * evidence), and the conversation is persisted server-side so it survives a
 * reload.
 */
export function ChatPage() {
  const { api, pushToast } = useApp();
  const [searchParams, setSearchParams] = useSearchParams();

  const requestedDocs = useMemo(() => {
    const raw = searchParams.get("docs") ?? "";
    return raw.split(",").map((value) => value.trim()).filter(Boolean);
  }, [searchParams]);

  const [selectedIds, setSelectedIds] = useState<string[]>(requestedDocs);
  const [question, setQuestion] = useState("");
  const [topK, setTopK] = useState(6);
  const [messages, setMessages] = useState<TranscriptMessage[]>([]);
  const [pending, setPending] = useState(false);
  const [askError, setAskError] = useState<ApiError | null>(null);
  const [openCitation, setOpenCitation] = useState<Citation | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(searchParams.get("conversation"));
  const [confirmClear, setConfirmClear] = useState(false);
  const [conversationsRefresh, setConversationsRefresh] = useState(0);

  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const transcriptEndRef = useRef<HTMLDivElement | null>(null);
  // The most recent failed turn, so "Try again" can re-ask exactly that question
  // instead of making the user retype it. Cleared on success or on retry.
  const lastFailureRef = useRef<{ question: string; userId: string; assistantId: string } | null>(null);
  // Conversation ids created by this browser session. Reloading one of those from
  // the server would replace the live transcript with the (much shorter) stored
  // history while an answer is still in flight, so they are never auto-reloaded.
  const sessionConversationRef = useRef<string | null>(null);

  const documents = usePolling<DocumentSummary[]>(() => api.listDocuments(), {
    intervalMs: 5000,
    maxIntervalMs: 15_000,
  });
  const conversations = usePolling<ConversationSummary[]>(() => api.listConversations(), {
    intervalMs: 10_000,
    maxIntervalMs: 30_000,
    refreshKey: conversationsRefresh,
  });
  const refreshConversations = useCallback(
    () => setConversationsRefresh((value) => value + 1),
    [],
  );

  // The welcome view may pass ?docs=... after an upload; keep in sync when it changes.
  useEffect(() => {
    setSelectedIds(requestedDocs);
  }, [requestedDocs]);

  // Ctrl/Cmd+K focuses the composer (advertised in the sidebar).
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        composerRef.current?.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  // Loading a *stored* conversation replaces the transcript with its history.
  useEffect(() => {
    if (!conversationId) return;
    if (sessionConversationRef.current === conversationId) return;
    let active = true;
    api
      .getConversation(conversationId)
      .then((conversation) => {
        if (!active) return;
        setMessages(
          conversation.messages.map((message) => ({
            id: message.id,
            role: message.role === "user" ? "user" : "assistant",
            content: message.content,
            createdAt: message.created_at,
            citations: message.citations,
            answerMode: message.answer_mode,
          })),
        );
        if (conversation.document_ids.length > 0) setSelectedIds(conversation.document_ids);
      })
      .catch((error: unknown) => {
        if (active) {
          pushToast({
            tone: "error",
            title: "Could not load that conversation",
            message: error instanceof Error ? error.message : String(error),
          });
        }
      });
    return () => {
      active = false;
    };
  }, [api, conversationId, pushToast]);

  const availableDocuments = documents.value ?? [];
  const documentsLoaded = documents.value !== null;
  const readyDocuments = availableDocuments.filter((document) => document.status === "ready");
  const readyIds = readyDocuments.map((document) => document.id);
  const effectiveSelection = selectedIds.filter((id) => readyIds.includes(id));

  const scrollToEnd = useCallback(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, []);

  async function ensureConversation(title: string): Promise<string | null> {
    if (conversationId) return conversationId;
    const title_ = title.slice(0, 60).trim() || "New conversation";
    try {
      const created = await api.createConversation(effectiveSelection, title_);
      sessionConversationRef.current = created.id;
      setConversationId(created.id);
      const next = new URLSearchParams(searchParams);
      next.set("conversation", created.id);
      setSearchParams(next, { replace: true });
      return created.id;
    } catch (error) {
      // Failing to persist the conversation must not block answering the question.
      pushToast({
        tone: "error",
        title: "Could not save the conversation",
        message: error instanceof Error ? error.message : String(error),
      });
      return null;
    }
  }

  async function submit(rawQuestion: string) {
    const trimmed = rawQuestion.trim();
    if (!trimmed || pending) return;
    // Only block once we *know* nothing is ready. Before the library has loaded, the
    // question is sent anyway — refusing to ask because a list has not arrived yet
    // would break the upload → ask flow for no reason.
    if (documentsLoaded && readyDocuments.length === 0) {
      setAskError(new ApiError("No ready documents to search. Upload one first.", { code: "no_documents" }));
      return;
    }

    const userMessage: TranscriptMessage = {
      id: `local-user-${Date.now()}`,
      role: "user",
      content: trimmed,
      createdAt: new Date().toISOString(),
      citations: [],
    };
    const pendingId = `local-assistant-${Date.now()}`;
    setMessages((current) => [
      ...current,
      userMessage,
      { id: pendingId, role: "assistant", content: "", createdAt: new Date().toISOString(), citations: [], pending: true },
    ]);
    setPending(true);
    setAskError(null);
    setQuestion("");
    setTimeout(scrollToEnd, 30);

    const scope = documentsLoaded
      ? resolveSearchScope(effectiveSelection, readyIds, availableDocuments.map((d) => d.id))
      : {
          ids: requestedDocs.length > 0 ? requestedDocs : null,
          single: requestedDocs.length === 1 ? requestedDocs[0]! : null,
        };
    const payload = {
      question: trimmed,
      document_ids: scope.ids,
      top_k: topK,
      conversation_id: null as string | null,
    };

    try {
      const activeConversation = await ensureConversation(trimmed);
      payload.conversation_id = activeConversation;

      // One document uses the document-scoped route; anything else uses the collection route.
      const answer = scope.single
        ? await api.askDocument(scope.single, payload)
        : await api.askCollection({ ...payload, document_ids: scope.ids });

      setMessages((current) =>
        current.map((message) =>
          message.id === pendingId
            ? {
                ...message,
                pending: false,
                content: answer.answer,
                citations: answer.citations,
                answerMode: answer.answer_mode,
                latencyMs: answer.latency_ms,
                notice: answer.notice,
              }
            : message,
        ),
      );
      lastFailureRef.current = null;
      if (answer.insufficient_evidence) {
        pushToast({
          tone: "info",
          title: "Not enough evidence in your documents",
          message: "The assistant declined to answer rather than guess. Try rephrasing or uploading a more relevant file.",
        });
      }
      setTimeout(scrollToEnd, 30);
      refreshConversations();
    } catch (error) {
      const apiError = error instanceof ApiError ? error : new ApiError(String(error), { code: "unexpected_error" });
      setAskError(apiError);
      lastFailureRef.current = { question: trimmed, userId: userMessage.id, assistantId: pendingId };
      setMessages((current) =>
        current.map((message) =>
          message.id === pendingId ? { ...message, pending: false, error: apiError.message } : message,
        ),
      );
    } finally {
      setPending(false);
    }
  }

  /** Re-asks the last failed question: drop the failed turn, then submit again. */
  function retryLast() {
    const failed = lastFailureRef.current;
    if (!failed || pending) return;
    lastFailureRef.current = null;
    setMessages((current) =>
      current.filter((message) => message.id !== failed.userId && message.id !== failed.assistantId),
    );
    setAskError(null);
    void submit(failed.question);
  }

  /**
   * Starts a fresh transcript without touching the stored conversations (they
   * stay in the "Recent conversations" list and can be reopened).
   */
  function startNewConversation() {
    if (pending) return;
    lastFailureRef.current = null;
    setMessages([]);
    setConversationId(null);
    sessionConversationRef.current = null;
    setAskError(null);
    const next = new URLSearchParams(searchParams);
    next.delete("conversation");
    setSearchParams(next, { replace: true });
    composerRef.current?.focus();
  }

  async function loadConversation(id: string) {
    // An explicit click always means "show me what is stored".
    sessionConversationRef.current = null;
    const next = new URLSearchParams(searchParams);
    next.set("conversation", id);
    setSearchParams(next);
    setConversationId(id);
  }

  async function clearHistory() {
    try {
      const result = await api.clearConversations();
      pushToast({
        tone: "success",
        title: "Conversation history cleared",
        message: `${result.conversations_removed} stored conversation${result.conversations_removed === 1 ? "" : "s"} removed from this machine.`,
      });
      setMessages([]);
      setConversationId(null);
      setSearchParams({}, { replace: true });
      refreshConversations();
    } catch (error) {
      pushToast({
        tone: "error",
        title: "Could not clear history",
        message: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setConfirmClear(false);
    }
  }

  const lastAssistant = [...messages].reverse().find((message) => message.role === "assistant" && !message.pending);

  return (
    <div className="main__inner">
      <div className="breadcrumbs">
        <span>Screen 04</span>
        <span className="breadcrumbs__sep">/</span>
        <span>Ask</span>
      </div>

      <header className="page-header">
        <h1>Ask your documents</h1>
        <p className="page-header__lede">
          Answers are assembled only from passages retrieved out of the documents you select. When nothing relevant is
          found you get an explicit &quot;insufficient evidence&quot; response instead of a guess.
        </p>
      </header>

      <div className="grid grid--2" style={{ alignItems: "start" }}>
        <div className="stack" style={{ minWidth: 0 }}>
          <Nova
            mood={pending ? "thinking" : askError ? "concerned" : "idle"}
            size={96}
            message={
              askError
                ? askError.message
                : pending
                  ? "Reading your documents and matching passages…"
                  : readyDocuments.length === 0
                    ? "I have no ready documents to search yet. Upload one and I will index it in seconds."
                    : `Ask me anything about ${effectiveSelection.length > 0 ? `${effectiveSelection.length} selected document${effectiveSelection.length === 1 ? "" : "s"}` : "all ready documents"}.`
            }
          />

          <Card title="Ask a question" tight>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void submit(question);
              }}
            >
              <TextAreaField
                ref={composerRef}
                label="Your question"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void submit(question);
                  }
                }}
                placeholder="e.g. What does the document say about error handling?"
                hint="Enter sends the question; Shift+Enter starts a new line. Press Ctrl+K to jump here from anywhere."
                rows={3}
              />
              <div className="row" style={{ marginTop: "var(--space-3)", alignItems: "flex-end" }}>
                <div style={{ width: 160 }}>
                  <NumberField
                    label="Passages (top k)"
                    value={topK}
                    min={1}
                    max={20}
                    onValueChange={setTopK}
                    hint="How many chunks to retrieve"
                  />
                </div>
                <div className="spacer" />
                <Button type="submit" variant="primary" loading={pending} loadingLabel="Thinking…">
                  Ask
                </Button>
              </div>
            </form>

            <div className="row" style={{ marginTop: "var(--space-3)" }}>
              <span className="field__label" style={{ margin: 0 }}>
                Try:
              </span>
              {SAMPLE_QUESTIONS.map((sample) => (
                <button
                  key={sample}
                  type="button"
                  className="btn btn--ghost btn--small"
                  onClick={() => {
                    setQuestion(sample);
                    void submit(sample);
                  }}
                  disabled={pending || readyDocuments.length === 0}
                >
                  {sample}
                </button>
              ))}
            </div>
          </Card>

          <Card title="Documents in scope" tight>
            {availableDocuments.length === 0 ? (
              <p className="text-muted" style={{ margin: 0 }}>
                No documents uploaded yet.
              </p>
            ) : (
              <>
                <div className="row">
                  <Button
                    size="small"
                    variant="ghost"
                    onClick={() => setSelectedIds([])}
                    disabled={selectedIds.length === 0}
                  >
                    Search everything
                  </Button>
                  <Button
                    size="small"
                    variant="ghost"
                    onClick={() => setSelectedIds(readyIds)}
                    disabled={readyIds.length === 0}
                  >
                    Select all ready
                  </Button>
                </div>
                <ul className="hint-list" style={{ listStyle: "none", paddingLeft: 0, marginTop: "var(--space-3)" }}>
                  {availableDocuments.map((document) => {
                    const selectable = document.status === "ready";
                    return (
                      <li key={document.id}>
                        <label style={{ display: "flex", gap: 8, alignItems: "center", cursor: selectable ? "pointer" : "not-allowed" }}>
                          <input
                            type="checkbox"
                            checked={selectedIds.includes(document.id)}
                            disabled={!selectable}
                            onChange={() =>
                              setSelectedIds((current) =>
                                current.includes(document.id)
                                  ? current.filter((value) => value !== document.id)
                                  : [...current, document.id],
                              )
                            }
                          />
                          <span style={{ overflowWrap: "anywhere" }}>{document.filename}</span>
                          <span className={`pill pill--${document.status}`}>{document.status}</span>
                        </label>
                      </li>
                    );
                  })}
                </ul>
                <p className="text-small text-dim" style={{ margin: 0 }}>
                  {effectiveSelection.length === 0
                    ? "No selection means every ready document is searched."
                    : `Searching ${effectiveSelection.length} document${effectiveSelection.length === 1 ? "" : "s"}.`}
                </p>
              </>
            )}
          </Card>

          <Card title="Recent conversations" tight>
            {conversations.value && conversations.value.length > 0 ? (
              <>
                <ul className="hint-list" style={{ listStyle: "none", paddingLeft: 0 }}>
                  {conversations.value.slice(0, 8).map((conversation) => (
                    <li key={conversation.id} style={{ marginBottom: 6 }}>
                      <button
                        type="button"
                        className="btn btn--ghost btn--small"
                        onClick={() => void loadConversation(conversation.id)}
                        style={{ width: "100%", justifyContent: "space-between" }}
                      >
                        <span style={{ overflowWrap: "anywhere" }}>{conversation.title}</span>
                        <span className="text-dim">{formatRelative(conversation.updated_at)}</span>
                      </button>
                    </li>
                  ))}
                </ul>
                <Button size="small" variant="danger" onClick={() => setConfirmClear(true)}>
                  Clear all history
                </Button>
              </>
            ) : (
              <p className="text-muted" style={{ margin: 0 }}>
                No saved conversations yet. Questions are stored locally so you can revisit the citations later.
              </p>
            )}
          </Card>
        </div>

        <div className="stack" style={{ minWidth: 0 }}>
          <Card
            title="Conversation"
            hint={`${messages.length} message${messages.length === 1 ? "" : "s"} in this session`}
            actions={
              messages.length > 0 ? (
                <Button size="small" variant="ghost" onClick={startNewConversation} disabled={pending}>
                  New conversation
                </Button>
              ) : null
            }
          >
            {askError && !messages.some((message) => message.error) ? (
              <div style={{ marginBottom: "var(--space-4)" }}>
                <ErrorState error={askError} title="The question could not be answered" />
              </div>
            ) : null}

            {messages.length === 0 ? (
              <Notice>
                Nothing asked yet. Pick the documents on the left — or leave every ready document in scope — and ask a
                question. Every answer sentence links back to the passage it came from.
              </Notice>
            ) : (
              <ChatTranscript
                messages={messages}
                onCitationClick={(citation) => setOpenCitation(citation)}
                onOpenSource={(citation) => setOpenCitation(citation)}
                onRetry={lastFailureRef.current ? retryLast : undefined}
                retryableMessageId={lastFailureRef.current?.assistantId ?? null}
              />
            )}
            <div ref={transcriptEndRef} />
          </Card>

          {lastAssistant?.answerMode === "insufficient" ? (
            <Notice tone="warn">
              The last question had no supporting evidence in the selected documents. That is a deliberate refusal: the
              system will not answer from outside knowledge.
            </Notice>
          ) : null}
        </div>
      </div>

      <SourceViewer citation={openCitation} onClose={() => setOpenCitation(null)} />

      <ConfirmDialog
        open={confirmClear}
        title="Clear all conversation history?"
        confirmLabel="Clear history"
        danger
        onCancel={() => setConfirmClear(false)}
        onConfirm={() => void clearHistory()}
      >
        <p style={{ marginTop: 0 }}>
          Every stored question, answer and citation for all conversations will be deleted from the local database.
          Documents and their vector index are not affected.
        </p>
      </ConfirmDialog>
    </div>
  );
}


