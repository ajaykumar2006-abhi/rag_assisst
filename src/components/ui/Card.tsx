import type { ReactNode } from "react";

export function Card({
  title,
  hint,
  children,
  accent = false,
  tight = false,
  actions,
  as: Tag = "section",
  className,
  titleId,
}: {
  title?: ReactNode;
  hint?: ReactNode;
  children: ReactNode;
  accent?: boolean;
  tight?: boolean;
  actions?: ReactNode;
  as?: "section" | "article" | "div";
  className?: string;
  /** Lets a surrounding <section aria-labelledby> point at this card's heading. */
  titleId?: string;
}) {
  const classes = ["card", accent ? "card--accent" : "", tight ? "card--tight" : "", className ?? ""]
    .filter(Boolean)
    .join(" ");

  return (
    <Tag className={classes}>
      {title || actions ? (
        <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            {title ? (
              <h2 className="card__title" id={titleId}>
                {title}
              </h2>
            ) : null}
            {hint ? <p className="card__hint">{hint}</p> : null}
          </div>
          {actions ? <div className="row row--end">{actions}</div> : null}
        </div>
      ) : null}
      {children}
    </Tag>
  );
}

export function Metric({
  label,
  value,
  note,
}: {
  label: string;
  value: ReactNode;
  note?: ReactNode;
}) {
  return (
    <div className="metric">
      <span className="metric__label">{label}</span>
      <span className="metric__value">{value}</span>
      {note ? <span className="metric__note">{note}</span> : null}
    </div>
  );
}
