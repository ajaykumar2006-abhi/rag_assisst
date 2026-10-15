/**
 * Hand-written inline SVG icons.
 *
 * Kept in one module so the app ships zero icon-font or icon-library
 * dependencies. All icons inherit `currentColor` and are marked decorative;
 * the surrounding control always carries the accessible name.
 */

export interface IconProps {
  className?: string;
}

const base = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.7,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
  focusable: false,
};

export function HomeIcon({ className = "nav__icon" }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M3 10.5 12 3l9 7.5" />
      <path d="M5 9.5V21h14V9.5" />
      <path d="M9.5 21v-6h5v6" />
    </svg>
  );
}

export function UploadIcon({ className = "nav__icon" }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M12 16V4" />
      <path d="m7.5 8.5 4.5-4.5 4.5 4.5" />
      <path d="M4 16v2.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V16" />
    </svg>
  );
}

export function PipelineIcon({ className = "nav__icon" }: IconProps) {
  return (
    <svg {...base} className={className}>
      <circle cx="6" cy="6" r="2.5" />
      <circle cx="18" cy="12" r="2.5" />
      <circle cx="6" cy="18" r="2.5" />
      <path d="M8.5 6h4.5a2.5 2.5 0 0 1 2.5 2.5v1" />
      <path d="M15.5 12.5v1A2.5 2.5 0 0 1 13 16H8.5" />
    </svg>
  );
}

export function ChatIcon({ className = "nav__icon" }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M20 15.5A2.5 2.5 0 0 1 17.5 18H8l-4 3v-4.5A2.5 2.5 0 0 1 4 15V7.5A2.5 2.5 0 0 1 6.5 5h11A2.5 2.5 0 0 1 20 7.5Z" />
      <path d="M8.5 10.5h7M8.5 13.5h4" />
    </svg>
  );
}

export function ChartIcon({ className = "nav__icon" }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M4 20V6" />
      <path d="M4 20h16" />
      <path d="M8 20v-6M12.5 20V9M17 20v-8" />
    </svg>
  );
}

export function ShieldIcon({ className = "nav__icon" }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M12 3l7.5 3v6c0 4.4-3.1 7.7-7.5 9-4.4-1.3-7.5-4.6-7.5-9V6Z" />
      <path d="m9 12 2.2 2.2L15.5 10" />
    </svg>
  );
}

export function TrashIcon({ className = "nav__icon" }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M4 7h16" />
      <path d="M9 7V5h6v2" />
      <path d="M6.5 7l.8 12a1.5 1.5 0 0 0 1.5 1.4h6.4a1.5 1.5 0 0 0 1.5-1.4L17.5 7" />
      <path d="M10.5 11v5.5M13.5 11v5.5" />
    </svg>
  );
}

export function RetryIcon({ className = "nav__icon" }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M20 11a8 8 0 1 0-2.4 5.7" />
      <path d="M20 5v6h-6" />
    </svg>
  );
}

export function SparkIcon({ className = "nav__icon" }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M12 3.5 13.8 9 19 10.8 13.8 12.6 12 18l-1.8-5.4L5 10.8 10.2 9Z" />
      <path d="M18 17.5l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7Z" />
    </svg>
  );
}

export function EyeIcon({ className = "nav__icon" }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M2.5 12S6 6.5 12 6.5S21.5 12 21.5 12S18 17.5 12 17.5S2.5 12 2.5 12Z" />
      <circle cx="12" cy="12" r="2.8" />
    </svg>
  );
}

export function NovaIcon({ className = "nav__icon" }: IconProps) {
  return (
    <svg {...base} className={className}>
      <rect x="4" y="6" width="16" height="12" rx="5" />
      <path d="M12 6V3" />
      <circle cx="9" cy="12" r="1.2" fill="currentColor" />
      <circle cx="15" cy="12" r="1.2" fill="currentColor" />
    </svg>
  );
}
