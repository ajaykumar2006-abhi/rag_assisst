import { useEffect, useRef, type ReactNode } from "react";

import { Button } from "./Button";

/**
 * Modal confirmation dialog.
 *
 * Behaviour that matters for safety: focus moves into the dialog when it opens,
 * Escape cancels, the Tab order is trapped inside, and the panel is labelled by
 * its own heading. Destructive confirmations require an explicit click on the
 * danger button — pressing Enter in the surrounding page cannot trigger them.
 */
export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  cancelLabel = "Cancel",
  danger = false,
  pending = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  children?: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  danger?: boolean;
  pending?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const headingId = `confirm-title-${title.replace(/\W+/g, "-").toLowerCase()}`;

  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const panel = panelRef.current;
    const focusable = panel?.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    );
    focusable?.[0]?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        if (!pending) onCancel();
        return;
      }
      if (event.key !== "Tab" || !panel) return;
      const items = Array.from(
        panel.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])',
        ),
      );
      if (items.length === 0) return;
      const first = items[0]!;
      const last = items[items.length - 1]!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
      previouslyFocused?.focus?.();
    };
  }, [open, onCancel, pending]);

  if (!open) return null;

  return (
    <div
      className="viewer"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !pending) onCancel();
      }}
    >
      <div className="viewer__panel viewer__panel--narrow" role="dialog" aria-modal="true" aria-labelledby={headingId} ref={panelRef}>
        <h2 id={headingId} style={{ marginBottom: "var(--space-3)" }}>
          {title}
        </h2>
        <div className="text-muted text-small">{children}</div>
        <div className="row row--end" style={{ marginTop: "var(--space-5)" }}>
          <Button variant="ghost" onClick={onCancel} disabled={pending}>
            {cancelLabel}
          </Button>
          <Button variant={danger ? "danger" : "primary"} onClick={onConfirm} loading={pending} loadingLabel="Working…">
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
