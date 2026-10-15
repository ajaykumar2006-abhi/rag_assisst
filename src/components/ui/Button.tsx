import { forwardRef, type ButtonHTMLAttributes } from "react";

import { Spinner } from "./Feedback";

export type ButtonVariant = "primary" | "default" | "ghost" | "danger";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: "default" | "small";
  /** Shows a spinner and disables the button while an action is in flight. */
  loading?: boolean;
  /** Accessible label shown while `loading` replaces the normal label. */
  loadingLabel?: string;
  icon?: React.ReactNode;
}

const VARIANT_CLASS: Record<ButtonVariant, string> = {
  primary: "btn btn--primary",
  default: "btn",
  ghost: "btn btn--ghost",
  danger: "btn btn--danger",
};

/**
 * The single button component used everywhere.
 *
 * While `loading` the button is disabled so an impatient double-click cannot
 * fire a second request, and `aria-busy` tells assistive tech why.
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "default", size = "default", loading = false, loadingLabel, icon, children, className, disabled, ...rest },
  ref,
) {
  const classes = [VARIANT_CLASS[variant], size === "small" ? "btn--small" : "", className ?? ""]
    .filter(Boolean)
    .join(" ");

  return (
    <button
      {...rest}
      ref={ref}
      className={classes}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
    >
      {loading ? <Spinner /> : icon}
      <span>{loading ? (loadingLabel ?? "Working…") : children}</span>
    </button>
  );
});
