import type { Toast } from "@/context/AppContext";

const TONE_LABEL: Record<Toast["tone"], string> = {
  info: "Notice",
  success: "Success",
  error: "Error",
};

/**
 * Live region for transient feedback.
 *
 * Errors are announced assertively and stay until dismissed so the user cannot
 * miss a failure; informational messages announce politely and auto-dismiss
 * (handled by the provider).
 */
export function ToastStack({
  toasts,
  onDismiss,
}: {
  toasts: Toast[];
  onDismiss: (id: string) => void;
}) {
  if (toasts.length === 0) return null;

  return (
    <div className="toasts">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`toast toast--${toast.tone}`}
          role={toast.tone === "error" ? "alert" : "status"}
          aria-live={toast.tone === "error" ? "assertive" : "polite"}
        >
          <div style={{ flex: 1 }}>
            <p className="toast__title">
              <span className="visually-hidden">{TONE_LABEL[toast.tone]}: </span>
              {toast.title}
            </p>
            {toast.message ? <p className="toast__message">{toast.message}</p> : null}
            {toast.retry ? (
              <button
                type="button"
                className="btn btn--small"
                style={{ marginTop: 8 }}
                onClick={() => {
                  onDismiss(toast.id);
                  toast.retry?.();
                }}
              >
                Retry
              </button>
            ) : null}
          </div>
          <button
            type="button"
            className="btn btn--ghost btn--small"
            onClick={() => onDismiss(toast.id)}
            aria-label={`Dismiss ${TONE_LABEL[toast.tone].toLowerCase()} message`}
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}
