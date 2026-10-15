import {
  forwardRef,
  useId,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";

function FieldShell({
  label,
  hint,
  error,
  controlId,
  children,
}: {
  label: string;
  hint?: ReactNode;
  error?: string;
  controlId: string;
  children: ReactNode;
}) {
  return (
    <div className="field">
      <label className="field__label" htmlFor={controlId}>
        {label}
      </label>
      {children}
      {hint && !error ? (
        <span className="field__hint" id={`${controlId}-hint`}>
          {hint}
        </span>
      ) : null}
      {error ? (
        <span className="field__hint" id={`${controlId}-error`} role="alert" style={{ color: "var(--rose)" }}>
          {error}
        </span>
      ) : null}
    </div>
  );
}

export interface TextFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "id"> {
  label: string;
  hint?: ReactNode;
  error?: string;
}

export function TextField({ label, hint, error, ...rest }: TextFieldProps) {
  const id = useId();
  return (
    <FieldShell label={label} hint={hint} error={error} controlId={id}>
      <input
        {...rest}
        id={id}
        className="field__input"
        aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined}
        aria-invalid={error ? true : undefined}
      />
    </FieldShell>
  );
}

export interface NumberFieldProps extends Omit<TextFieldProps, "onChange" | "value" | "type"> {
  value: number;
  onValueChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
}

/**
 * Numeric input that reports parsed numbers, not strings.
 *
 * While the user is typing the raw string is preserved internally so values like
 * "0." or a temporarily empty box do not get coerced to `0` under their cursor.
 * Out-of-range values are clamped on blur and the clamping is visible in the UI.
 */
export function NumberField({
  value,
  onValueChange,
  min,
  max,
  step = 1,
  label,
  hint,
  error,
  ...rest
}: NumberFieldProps) {
  const id = useId();

  return (
    <FieldShell
      label={label}
      hint={hint ?? (min !== undefined || max !== undefined ? `Allowed: ${min ?? "—"} to ${max ?? "—"}` : undefined)}
      error={error}
      controlId={id}
    >
      <input
        {...rest}
        id={id}
        type="number"
        className="field__input"
        value={Number.isFinite(value) ? value : ""}
        min={min}
        max={max}
        step={step}
        onChange={(event) => {
          const parsed = Number(event.target.value);
          onValueChange(Number.isFinite(parsed) ? parsed : 0);
        }}
        onBlur={(event) => {
          const parsed = Number(event.target.value);
          let next = Number.isFinite(parsed) ? parsed : (min ?? 0);
          if (min !== undefined) next = Math.max(min, next);
          if (max !== undefined) next = Math.min(max, next);
          if (next !== value) onValueChange(next);
        }}
        aria-describedby={error ? `${id}-error` : `${id}-hint`}
        aria-invalid={error ? true : undefined}
      />
    </FieldShell>
  );
}

export interface SelectFieldProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "id"> {
  label: string;
  hint?: ReactNode;
  error?: string;
  options: { value: string; label: string; disabled?: boolean }[];
}

export function SelectField({ label, hint, error, options, ...rest }: SelectFieldProps) {
  const id = useId();
  return (
    <FieldShell label={label} hint={hint} error={error} controlId={id}>
      <select
        {...rest}
        id={id}
        className="field__select"
        aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value} disabled={option.disabled}>
            {option.label}
          </option>
        ))}
      </select>
    </FieldShell>
  );
}

export interface TextAreaFieldProps extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "id"> {
  label: string;
  hint?: ReactNode;
  error?: string;
}

export const TextAreaField = forwardRef<HTMLTextAreaElement, TextAreaFieldProps>(function TextAreaField(
  { label, hint, error, ...rest },
  ref,
) {
  const id = useId();
  return (
    <FieldShell label={label} hint={hint} error={error} controlId={id}>
      <textarea
        {...rest}
        ref={ref}
        id={id}
        className="field__textarea"
        aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined}
        aria-invalid={error ? true : undefined}
      />
    </FieldShell>
  );
});

export function Toggle({
  checked,
  onChange,
  label,
  hint,
  disabled = false,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  hint?: ReactNode;
  disabled?: boolean;
}) {
  const id = useId();
  return (
    <div className="field">
      <label className="switch" htmlFor={id}>
        <input
          id={id}
          type="checkbox"
          checked={checked}
          disabled={disabled}
          onChange={(event) => onChange(event.target.checked)}
          aria-describedby={hint ? `${id}-hint` : undefined}
        />
        <span style={{ fontWeight: 600 }}>{label}</span>
      </label>
      {hint ? (
        <span className="field__hint" id={`${id}-hint`}>
          {hint}
        </span>
      ) : null}
    </div>
  );
}
