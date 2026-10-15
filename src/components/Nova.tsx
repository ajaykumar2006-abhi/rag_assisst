import { memo } from "react";

/**
 * Nova — the application's cartoon AI assistant.
 *
 * Nova is an original character drawn entirely in inline SVG (no image assets,
 * no external fonts, no third-party art). She is a glass-helmeted star-navigator
 * whose expression and motion change with the app state:
 *
 *   idle        calm, awake, gently floating
 *   thinking    eyes narrowed, brow raised, faster float
 *   happy       warm smile, elevated antenna glow
 *   concerned   flat mouth, tilted brow — used when something failed
 *
 * The `size` prop scales the whole figure; the figure is decorative so it is
 * `aria-hidden`, and every message Nova "says" is rendered as real text in the
 * speech bubble beside it.
 */

export type NovaMood = "idle" | "thinking" | "happy" | "concerned";

export interface NovaProps {
  mood?: NovaMood;
  /** Optional speech-bubble text. When omitted only the figure is drawn. */
  message?: string;
  size?: number;
  /** Hide the bubble on narrow screens for short, decorative placements. */
  hideBubbleOnMobile?: boolean;
  className?: string;
}

const MOOD_LABELS: Record<NovaMood, string> = {
  idle: "Nova is idle",
  thinking: "Nova is thinking",
  happy: "Nova is pleased",
  concerned: "Nova is concerned",
};

function Eyes({ mood }: { mood: NovaMood }) {
  if (mood === "happy") {
    return (
      <>
        {/* Upturned, closed-happy eyes drawn as arcs. */}
        <path d="M46 62 Q52 55 58 62" stroke="#0b1030" strokeWidth="3.4" fill="none" strokeLinecap="round" />
        <path d="M70 62 Q76 55 82 62" stroke="#0b1030" strokeWidth="3.4" fill="none" strokeLinecap="round" />
      </>
    );
  }
  if (mood === "thinking") {
    return (
      <>
        <ellipse cx="52" cy="62" rx="4.6" ry="3.2" fill="#0b1030" />
        <ellipse cx="76" cy="62" rx="4.6" ry="3.2" fill="#0b1030" />
        <path d="M44 52 Q52 47 59 51" stroke="#0b1030" strokeWidth="2.6" fill="none" strokeLinecap="round" />
        <path d="M69 49 Q77 45 85 50" stroke="#0b1030" strokeWidth="2.6" fill="none" strokeLinecap="round" />
      </>
    );
  }
  if (mood === "concerned") {
    return (
      <>
        <ellipse cx="52" cy="63" rx="4.4" ry="4.4" fill="#0b1030" />
        <ellipse cx="76" cy="63" rx="4.4" ry="4.4" fill="#0b1030" />
        <path d="M43 51 L60 55" stroke="#0b1030" strokeWidth="2.6" fill="none" strokeLinecap="round" />
        <path d="M85 51 L68 55" stroke="#0b1030" strokeWidth="2.6" fill="none" strokeLinecap="round" />
      </>
    );
  }
  // idle: open, curious eyes with a highlight
  return (
    <>
      <ellipse cx="52" cy="62" rx="5.4" ry="6" fill="#0b1030" />
      <ellipse cx="76" cy="62" rx="5.4" ry="6" fill="#0b1030" />
      <circle cx="54" cy="59.5" r="1.7" fill="#dff3ff" />
      <circle cx="78" cy="59.5" r="1.7" fill="#dff3ff" />
    </>
  );
}

function Mouth({ mood }: { mood: NovaMood }) {
  if (mood === "happy") {
    return <path d="M55 76 Q64 86 73 76" stroke="#0b1030" strokeWidth="3.2" fill="none" strokeLinecap="round" />;
  }
  if (mood === "thinking") {
    return <path d="M57 78 Q64 81 71 78" stroke="#0b1030" strokeWidth="2.8" fill="none" strokeLinecap="round" />;
  }
  if (mood === "concerned") {
    return <path d="M56 80 Q64 76 72 80" stroke="#0b1030" strokeWidth="2.8" fill="none" strokeLinecap="round" />;
  }
  return <path d="M56 77 Q64 83 72 77" stroke="#0b1030" strokeWidth="3" fill="none" strokeLinecap="round" />;
}

export const Nova = memo(function Nova({
  mood = "idle",
  message,
  size = 116,
  hideBubbleOnMobile = false,
  className,
}: NovaProps) {
  return (
    <div
      className={`nova${mood === "thinking" ? " nova--thinking" : ""}${className ? ` ${className}` : ""}`}
      role="group"
      aria-label={MOOD_LABELS[mood]}
    >
      <div className="nova__figure nova__float" style={{ width: size, height: size * 1.16 }}>
        <svg
          viewBox="0 0 128 148"
          width={size}
          height={size * 1.16}
          aria-hidden="true"
          focusable="false"
        >
          <defs>
            <linearGradient id="nova-body" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="#c4b5fd" />
              <stop offset="55%" stopColor="#8b5cf6" />
              <stop offset="100%" stopColor="#60a5fa" />
            </linearGradient>
            <linearGradient id="nova-visor" x1="0" y1="0" x2="0.4" y2="1">
              <stop offset="0%" stopColor="#e8f6ff" />
              <stop offset="100%" stopColor="#a5cdf5" />
            </linearGradient>
            <radialGradient id="nova-glow" cx="0.5" cy="0.5" r="0.5">
              <stop offset="0%" stopColor="#fde68a" stopOpacity="0.95" />
              <stop offset="100%" stopColor="#f59e0b" stopOpacity="0" />
            </radialGradient>
          </defs>

          {/* antenna */}
          <line x1="64" y1="26" x2="64" y2="12" stroke="#c7d2fe" strokeWidth="3" strokeLinecap="round" />
          <circle cx="64" cy="9" r="11" fill="url(#nova-glow)" />
          <circle cx="64" cy="9" r="4.6" fill={mood === "happy" ? "#fde68a" : "#22d3ee"} />

          {/* head */}
          <rect x="26" y="24" width="76" height="66" rx="26" fill="url(#nova-body)" />
          <rect
            x="26"
            y="24"
            width="76"
            height="66"
            rx="26"
            fill="none"
            stroke="rgba(255,255,255,0.45)"
            strokeWidth="1.6"
          />
          {/* visor */}
          <rect x="38" y="44" width="52" height="34" rx="16" fill="url(#nova-visor)" opacity="0.94" />
          <Eyes mood={mood} />
          <Mouth mood={mood} />

          {/* neck + body */}
          <rect x="58" y="88" width="12" height="10" fill="#6d5bd0" />
          <rect x="34" y="96" width="60" height="42" rx="20" fill="url(#nova-body)" />
          <rect
            x="34"
            y="96"
            width="60"
            height="42"
            rx="20"
            fill="none"
            stroke="rgba(255,255,255,0.35)"
            strokeWidth="1.4"
          />
          {/* chest core pulses with state */}
          <circle cx="64" cy="117" r="7.5" fill="#0b1030" opacity="0.35" />
          <circle cx="64" cy="117" r="4.4" fill={mood === "concerned" ? "#fb7185" : "#34d399"}>
            {mood === "thinking" ? (
              <animate attributeName="opacity" values="1;0.35;1" dur="1.1s" repeatCount="indefinite" />
            ) : null}
          </circle>

          {/* arms */}
          <rect
            x="20"
            y="104"
            width="16"
            height="9"
            rx="4.5"
            fill="#7c6ce0"
            transform={mood === "happy" ? "rotate(-18 28 108)" : "rotate(0 28 108)"}
          />
          <rect
            x="92"
            y="104"
            width="16"
            height="9"
            rx="4.5"
            fill="#7c6ce0"
            transform={mood === "happy" ? "rotate(18 100 108)" : "rotate(0 100 108)"}
          />
        </svg>
      </div>

      {message ? (
        <p className={`nova__bubble${hideBubbleOnMobile ? " nova__bubble--hide-mobile" : ""}`}>
          {message}
        </p>
      ) : null}
    </div>
  );
});
