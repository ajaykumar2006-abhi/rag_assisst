import type { ReactNode } from "react";

import { ApiError } from "@/services/client";

/** Small indeterminate spinner. Hides itself from assistive tech (the parent states the busy reason). */
export function Spinner({ label }: { label?: string }) {
  return (
    <>
      <span className="spinner" aria-hidden="true" />
      {label ? <span className="visually-hidden">{label}</span> : null}
    </>
  );
}

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <p className="empty-state__title">{title}</p>
      {children ? <p className="text-muted">{children}</p> : null}
      {action ? <div className="row" style={{ justifyContent: "center" }}>{action}</div> : null}
    </div>
  );
}

/**
 * Renders the *real* failure the API reported: the human message, the HTTP
 * status and the machine-readable error code. A "Try again" action is offered
 * only when retrying can plausibly help (network errors and 5xx responses).
 */
export function ErrorState({
  error,
  title = "Something went wrong",
  onRetry,
}: {
  error: ApiError | Error;
  title?: string;
  onRetry?: () => void;
}) {
  const apiError = error instanceof ApiError ? error : null;
  const message = error.message || "The request failed and no message was provided.";

  return (
    <div className="error-state" role="alert">
      <h3 style={{ marginBottom: 4 }}>{title}</h3>
      <p style={{ marginBottom: 6 }}>{message}</p>
      {apiError ? (
        <p className="error-state__code">
          code: {apiError.code}
          {apiError.status ? ` · http ${apiError.status}` : " · no response"}
        </p>
      ) : null}
      {apiError?.retryable && onRetry ? (
        <div className="row" style={{ marginTop: 10 }}>
          <button type="button" className="btn btn--small" onClick={onRetry}>
            Try again
          </button>
        </div>
      ) : null}
    </div>
  );
}

/** Neutral informational row used for warnings the backend reports. */
export function Notice({ tone = "info", children }: { tone?: "info" | "warn"; children: ReactNode }) {
  const borderColor = tone === "warn" ? "rgba(251,191,36,0.5)" : "var(--border)";
  return (
    <p
      style={{
        margin: 0,
        padding: "10px 12px",
        border: `1px solid ${borderColor}`,
        borderRadius: "var(--radius)",
        background: "rgba(12,16,40,0.55)",
        fontSize: "0.86rem",
        color: "var(--text-muted)",
      }}
    >
      {children}
    </p>
  );
}

/** Renders a list of strings as a tight bulleted list of hints/limitations. */
export function BulletList({ items, label }: { items: string[]; label?: string }) {
  if (items.length === 0) return null;
  return (
    <div>
      {label ? <p className="field__label">{label}</p> : null}
      <ul className="hint-list">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}
