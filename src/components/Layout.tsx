import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

import { useApp } from "@/context/AppContext";
import { formatUptime } from "@/services/format";
import {
  ChartIcon,
  ChatIcon,
  HomeIcon,
  PipelineIcon,
  ShieldIcon,
  SparkIcon,
  UploadIcon,
} from "./icons";
import { ToastStack } from "./ui/ToastStack";

const NAV_ITEMS = [
  { to: "/", label: "Welcome", icon: <HomeIcon />, step: "01", end: true },
  { to: "/documents", label: "Documents", icon: <UploadIcon />, step: "02", end: false },
  { to: "/processing", label: "Processing", icon: <PipelineIcon />, step: "03", end: false },
  { to: "/chat", label: "Ask", icon: <ChatIcon />, step: "04", end: false },
  { to: "/evaluation", label: "Evaluation", icon: <ChartIcon />, step: "05", end: false },
  { to: "/settings", label: "Settings & privacy", icon: <ShieldIcon />, step: "06", end: false },
];

function linkClass({ isActive }: { isActive: boolean }) {
  return `nav__link${isActive ? " nav__link--active" : ""}`;
}

/**
 * Application shell: persistent navigation, a live backend indicator and the
 * toast region. Screen content is passed in as children so every page inherits
 * the same frame, breadcrumb position and focus target (`#main`).
 */
export function Layout({ children }: { children: ReactNode }) {
  const { health, healthError, backendOnline, motionEnabled, toggleMotion, toasts, dismissToast } = useApp();

  const statusTone = backendOnline ? "online" : healthError ? "offline" : "processing";
  const statusText = backendOnline
    ? "Backend online"
    : healthError
      ? "Backend unreachable"
      : "Checking backend…";

  return (
    <div className={`app-shell${motionEnabled ? "" : " motion-off"}`}>
      <aside className="sidebar">
        <div className="sidebar__brand">
          <span style={{ width: 34, height: 34, display: "grid", placeItems: "center", color: "var(--violet-bright)" }}>
            <SparkIcon className="" />
          </span>
          <div>
            <p className="sidebar__title">RAG Document Intelligence</p>
            <p className="sidebar__subtitle">Galaxy Edition</p>
          </div>
        </div>

        <nav className="nav" aria-label="Main navigation">
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.to} to={item.to} className={linkClass} end={item.end} data-testid={`nav-${item.step}`}>
              <span style={{ width: 20, height: 20, display: "inline-flex" }}>{item.icon}</span>
              <span>{item.label}</span>
              <span className="nav__step">{item.step}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar__footer">
          <div className="card card--tight" style={{ padding: "var(--space-3)" }}>
            <p className="metric__label" style={{ marginBottom: 6 }}>
              System
            </p>
            <p style={{ margin: "0 0 6px" }}>
              <span className={`pill pill--${statusTone}`} title={healthError?.message ?? undefined}>
                {statusText}
              </span>
            </p>
            {health ? (
              <ul className="hint-list" style={{ fontSize: "0.78rem" }}>
                <li>
                  Embeddings: <span className="mono">{health.embedding_provider}</span>
                </li>
                <li>
                  Answers: <span className="mono">{health.answer_provider}</span>
                </li>
                <li>
                  Indexed docs: <span className="mono">{health.documents_indexed}</span>
                </li>
                <li>
                  Uptime: <span className="mono">{formatUptime(health.uptime_seconds)}</span>
                </li>
              </ul>
            ) : healthError ? (
              <p className="text-small text-dim" style={{ margin: 0 }}>
                {healthError.message}
              </p>
            ) : null}
          </div>

          <label className="switch" htmlFor="motion-toggle">
            <input
              id="motion-toggle"
              type="checkbox"
              checked={motionEnabled}
              onChange={toggleMotion}
              aria-describedby="motion-hint"
            />
            <span className="text-small">Animations</span>
          </label>
          <p className="text-small text-dim" id="motion-hint" style={{ margin: 0 }}>
            Turn off to stop all Galaxy motion. Your choice is remembered.
          </p>
          <p className="text-small text-dim" style={{ margin: 0 }}>
            <code className="mono">Ctrl</code> + <code className="mono">K</code> opens Ask.
          </p>
        </div>
      </aside>

      <main className="main" id="main" tabIndex={-1}>
        {children}
      </main>

      <ToastStack toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}
