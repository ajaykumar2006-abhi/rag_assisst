import type { AnswerMode, DocumentStatus, StageState } from "@/types/api";
import { answerModeLabel, statusLabel, stageStateLabel } from "@/services/format";

export function Pill({
  tone = "neutral",
  children,
  title,
}: {
  tone?: string;
  children: React.ReactNode;
  title?: string;
}) {
  return (
    <span className={`pill pill--${tone}`} title={title}>
      {children}
    </span>
  );
}

export function StatusPill({ status }: { status: DocumentStatus }) {
  return <Pill tone={status}>{statusLabel(status)}</Pill>;
}

export function StagePill({ state }: { state: StageState }) {
  return <Pill tone={state}>{stageStateLabel(state)}</Pill>;
}

export function AnswerModePill({ mode }: { mode: AnswerMode }) {
  return <Pill tone={mode}>{answerModeLabel(mode)}</Pill>;
}

export function ProgressBar({
  value = 0,
  label,
  detail,
  indeterminate = false,
}: {
  /** Completion fraction in the range 0..1. */
  value?: number;
  label?: string;
  detail?: string;
  /** True while the total amount of work is not yet known. */
  indeterminate?: boolean;
}) {
  const clamped = Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 0;
  const percent = Math.round(clamped * 100);

  return (
    <div
      className="progress"
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={indeterminate ? undefined : percent}
      aria-label={label ?? "Progress"}
    >
      <div className="progress__track">
        <div
          className="progress__bar"
          style={{
            width: `${indeterminate ? 100 : percent}%`,
            opacity: indeterminate ? 0.55 : 1,
            transition: indeterminate ? "none" : undefined,
          }}
        />
      </div>
      {label || detail ? (
        <div className="progress__meta">
          <span>{label}</span>
          <span>{detail ?? `${percent}%`}</span>
        </div>
      ) : null}
    </div>
  );
}
