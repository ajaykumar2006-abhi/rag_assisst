import { useId, useRef, useState, type DragEvent } from "react";

import { formatBytes } from "@/services/format";

export interface RejectedFile {
  name: string;
  reason: string;
}

export interface DocumentDropzoneProps {
  onFiles: (files: File[]) => void;
  /** Extensions without the dot, e.g. ["pdf", "txt", "docx"]. */
  allowedExtensions: string[];
  maxBytes: number;
  disabled?: boolean;
  busy?: boolean;
  /** Optional label override for the call to action. */
  ctaLabel?: string;
}

/**
 * Upload target with the same validation rules the backend enforces.
 *
 * Validating in the browser first means an oversized or unsupported file gives
 * instant, specific feedback instead of a 413/415 after a long upload. The
 * server still validates independently — this is a convenience, not the control.
 */
export function DocumentDropzone({
  onFiles,
  allowedExtensions,
  maxBytes,
  disabled = false,
  busy = false,
  ctaLabel = "Choose files",
}: DocumentDropzoneProps) {
  const inputId = useId();
  const [dragActive, setDragActive] = useState(false);
  const [rejected, setRejected] = useState<RejectedFile[]>([]);
  const dragDepth = useRef(0);

  const accept = allowedExtensions.map((extension) => `.${extension}`).join(",");
  const isBlocked = disabled || busy;

  function handleSelection(list: FileList | null) {
    if (!list || list.length === 0) return;
    const accepted: File[] = [];
    const problems: RejectedFile[] = [];

    for (const file of Array.from(list)) {
      const extension = file.name.includes(".") ? file.name.split(".").pop()!.toLowerCase() : "";
      if (!allowedExtensions.includes(extension)) {
        problems.push({
          name: file.name,
          reason: `Unsupported type ".${extension || "unknown"}". Allowed: ${allowedExtensions.join(", ")}.`,
        });
        continue;
      }
      if (file.size === 0) {
        problems.push({ name: file.name, reason: "The file is empty." });
        continue;
      }
      if (file.size > maxBytes) {
        problems.push({
          name: file.name,
          reason: `Too large (${formatBytes(file.size)}). The limit is ${formatBytes(maxBytes)}.`,
        });
        continue;
      }
      accepted.push(file);
    }

    setRejected(problems);
    if (accepted.length > 0) onFiles(accepted);
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    dragDepth.current = 0;
    setDragActive(false);
    if (isBlocked) return;
    handleSelection(event.dataTransfer?.files ?? null);
  }

  const hint = allowedExtensions.map((extension) => extension.toUpperCase()).join(", ");

  return (
    <div>
      <div
        className={`dropzone${dragActive ? " dropzone--active" : ""}`}
        aria-disabled={isBlocked}
        onDragEnter={(event) => {
          event.preventDefault();
          dragDepth.current += 1;
          if (!isBlocked) setDragActive(true);
        }}
        onDragOver={(event) => {
          event.preventDefault();
        }}
        onDragLeave={(event) => {
          event.preventDefault();
          dragDepth.current = Math.max(0, dragDepth.current - 1);
          if (dragDepth.current === 0) setDragActive(false);
        }}
        onDrop={onDrop}
      >
        <input
          id={inputId}
          className="visually-hidden"
          type="file"
          multiple
          accept={accept}
          disabled={isBlocked}
          onChange={(event) => {
            handleSelection(event.target.files);
            // Reset so selecting the same file twice still fires a change event.
            event.target.value = "";
          }}
          data-testid="file-input"
        />
        <p className="dropzone__icon" aria-hidden="true">
          🛰️
        </p>
        <p style={{ margin: "0 0 4px", fontWeight: 600 }}>
          <label htmlFor={inputId} style={{ cursor: "pointer", textDecoration: "underline" }}>
            {busy ? "Uploading…" : ctaLabel}
          </label>{" "}
          or drop documents here
        </p>
        <p className="dropzone__hint">
          {hint} · up to {formatBytes(maxBytes)} per file. Files stay on this machine.
        </p>
      </div>

      {rejected.length > 0 ? (
        <div className="error-state" role="alert" style={{ marginTop: "var(--space-3)" }}>
          <h3 style={{ marginBottom: 4 }}>Some files were not added</h3>
          <ul className="hint-list">
            {rejected.map((item) => (
              <li key={`${item.name}-${item.reason}`}>
                <strong>{item.name}</strong> — {item.reason}
              </li>
            ))}
          </ul>
          <button type="button" className="btn btn--small" style={{ marginTop: 8 }} onClick={() => setRejected([])}>
            Dismiss
          </button>
        </div>
      ) : null}
    </div>
  );
}
