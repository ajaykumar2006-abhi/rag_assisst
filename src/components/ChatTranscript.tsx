import { Fragment, useEffect, useRef, useState } from "react";

import type { AnswerMode, Citation } from "@/types/api";
import { formatMilliseconds, formatRelative, parseAnswerSegments } from "@/services/format";
import { Nova } from "./Nova";
import { CitationCard } from "./CitationCard";
import { AnswerModePill } from "./ui/Pill";

export interface TranscriptMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: string;
  citations: Citation[];
  answerMode?: AnswerMode | null;
  latencyMs?: number | null;
  /** Non-fatal warnings the backend attached to this answer. */
  notice?: string | null;
  /** True while the answer is still streaming in (used for the thinking row). */
  pending?: boolean;
  /** Set when the question failed; shown in place of an answer. */
  error?: string | null;
}

export interface ChatTranscriptProps {
  messages: TranscriptMessage[];
  onCitationClick: (citation: Citation) => void;
  /** Covered by the scroll container; skips redundant re-renders of long lists. */
  onOpenSource?: (citation: Citation) => void;
  /** Re-asks the question whose answer failed. Omitted when retry is unsafe. */
  onRetry?: () => void;
  /** Only the most recent failed turn is retryable; older failures stay readable. */
  retryableMessageId?: string | null;
}

/**
 * Copy text to the clipboard, falling back to a hidden textarea when the
 * async Clipboard API is unavailable (older browsers, non-secure contexts).
 * Returns false instead of throwing so the UI can say so honestly.
 */
async function copyText(value: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch {
    // fall through to the legacy path
  }
  try {
    const scratch = document.createElement("textarea");
    scratch.value = value;
    scratch.setAttribute("readonly", "");
    scratch.style.position = "fixed";
    scratch.style.opacity = "0";
    document.body.appendChild(scratch);
    scratch.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(scratch);
    return ok;
  } catch {
    return false;
  }
}

/**
 * Renders the question/answer history.
 *
 * `[n]` markers inside an answer are turned into real buttons that scroll to and
 * outline the matching source card, so a claim in the answer can always be
 * traced back to the passage it came from.
 */
export function ChatTranscript({ messages, onCitationClick, onOpenSource, onRetry, retryableMessageId }: ChatTranscriptProps) {
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const copyTimerRef = useRef<number | null>(null);
  const [copyFailedId, setCopyFailedId] = useState<string | null>(null);

  useEffect(
    () => () => {
      if (copyTimerRef.current !== null) window.clearTimeout(copyTimerRef.current);
    },
    [],
  );

  async function handleCopy(message: TranscriptMessage) {
    const ok = await copyText(message.content);
    if (!ok) {
      setCopyFailedId(message.id);
      setCopiedId(null);
      return;
    }
    setCopyFailedId(null);
    setCopiedId(message.id);
    if (copyTimerRef.current !== null) window.clearTimeout(copyTimerRef.current);
    copyTimerRef.current = window.setTimeout(() => {
      setCopiedId((current) => (current === message.id ? null : current));
    }, 2000);
  }

  return (
    <ol className="transcript" data-testid="transcript">
      {messages.map((message) => {
        const isUser = message.role === "user";
        return (
          <li key={message.id} className={`message message--${isUser ? "user" : "assistant"}`}>
            <div className="message__avatar" aria-hidden="true">
              {isUser ? "You" : "N"}
            </div>
            <div className="message__body">
              <div className="message__meta">
                <span style={{ fontWeight: 600 }}>{isUser ? "You" : "Nova"}</span>
                <span>{formatRelative(message.createdAt)}</span>
                {message.answerMode ? <AnswerModePill mode={message.answerMode} /> : null}
                {typeof message.latencyMs === "number" ? (
                  <span>answered in {formatMilliseconds(message.latencyMs)}</span>
                ) : null}
                {!isUser && !message.pending && !message.error && message.content ? (
                  <button
                    type="button"
                    className="btn btn--ghost btn--small"
                    onClick={() => void handleCopy(message)}
                    aria-label="Copy this answer to the clipboard"
                  >
                    {copiedId === message.id ? "Copied ✓" : copyFailedId === message.id ? "Copy failed" : "Copy answer"}
                  </button>
                ) : null}
              </div>

              {message.pending ? (
                <div className="nova nova--thinking" aria-live="polite">
                  <Nova mood="thinking" size={64} hideBubbleOnMobile />
                  <p style={{ margin: 0 }} className="text-muted">
                    Searching your documents and assembling an answer with citations…
                  </p>
                </div>
              ) : message.error ? (
                <div className="error-state" role="alert">
                  <h4 style={{ marginTop: 0, marginBottom: 4 }}>This question failed</h4>
                  <p style={{ marginBottom: 0 }}>{message.error}</p>
                  {onRetry && retryableMessageId === message.id ? (
                    <p style={{ marginBottom: 0, marginTop: "var(--space-3)" }}>
                      <button type="button" className="btn btn--small" onClick={onRetry}>
                        Try again
                      </button>
                    </p>
                  ) : null}
                </div>
              ) : (
                <>
                  <div className="message__text">
                    {isUser
                      ? message.content
                      : parseAnswerSegments(message.content).map((segment, index) => {
                          if (segment.kind === "text") {
                            return <Fragment key={index}>{segment.value}</Fragment>;
                          }
                          const citation = message.citations.find((item) => item.index === segment.index);
                          return (
                            <button
                              key={index}
                              type="button"
                              className="citation-marker"
                              onClick={() => citation && onCitationClick(citation)}
                              disabled={!citation}
                              title={
                                citation
                                  ? `${citation.filename}${citation.page !== null ? ` — page ${citation.page}` : ""}`
                                  : "No matching source"
                              }
                              aria-label={
                                citation
                                  ? `Show source ${segment.index}: ${citation.filename}`
                                  : `Source ${segment.index} is not available`
                              }
                            >
                              {segment.value}
                            </button>
                          );
                        })}
                  </div>

                  {message.notice ? (
                    <p className="text-small text-dim" style={{ marginTop: "var(--space-3)", marginBottom: 0 }}>
                      {message.notice}
                    </p>
                  ) : null}

                  {message.citations.length > 0 ? (
                    <div className="stack" style={{ marginTop: "var(--space-4)" }}>
                      <p className="field__label" style={{ margin: 0 }}>
                        Sources used ({message.citations.length})
                      </p>
                      {message.citations.map((citation) => (
                        <CitationCard
                          key={`${message.id}-${citation.index}-${citation.chunk_id}`}
                          citation={citation}
                          onOpen={onOpenSource}
                        />
                      ))}
                    </div>
                  ) : !isUser && message.answerMode === "insufficient" ? (
                    <p className="text-small text-dim" style={{ marginTop: "var(--space-3)", marginBottom: 0 }}>
                      No passage in your documents was relevant enough to support an answer, so none was invented.
                    </p>
                  ) : null}
                </>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
