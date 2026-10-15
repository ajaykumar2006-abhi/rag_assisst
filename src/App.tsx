import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useEffect } from "react";

import { ErrorBoundary } from "@/components/ErrorBoundary";
import { GalaxyBackground } from "@/components/GalaxyBackground";
import { Layout } from "@/components/Layout";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/Feedback";
import { Card } from "@/components/ui/Card";
import { AppProvider, useApp } from "@/context/AppContext";
import { ChatPage } from "@/pages/ChatPage";
import { DocumentsPage } from "@/pages/DocumentsPage";
import { EvaluationPage } from "@/pages/EvaluationPage";
import { ProcessingPage } from "@/pages/ProcessingPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { WelcomePage } from "@/pages/WelcomePage";

function NotFoundPage() {
  return (
    <div className="main__inner">
      <Card title="That screen does not exist">
        <EmptyState title="404 — no route matched">
          The six screens are: welcome, documents, processing, ask, evaluation and settings.
        </EmptyState>
        <div className="row" style={{ justifyContent: "center" }}>
          <Button variant="primary" onClick={() => window.location.assign("/")}>
            Go to the welcome screen
          </Button>
        </div>
      </Card>
    </div>
  );
}

/**
 * Moves focus to the main region on every navigation.
 *
 * Without this, a keyboard or screen-reader user stays on the link they clicked
 * and has no signal that the page changed — the single most common SPA
 * accessibility failure.
 */
function RouteAnnouncer() {
  const location = useLocation();

  useEffect(() => {
    const main = document.getElementById("main");
    if (!main) return;
    // Keep the document title in step with the visible screen.
    const titles: Record<string, string> = {
      "/": "Welcome · RAG Document Intelligence",
      "/documents": "Documents · RAG Document Intelligence",
      "/processing": "Processing · RAG Document Intelligence",
      "/chat": "Ask · RAG Document Intelligence",
      "/evaluation": "Evaluation · RAG Document Intelligence",
      "/settings": "Settings & privacy · RAG Document Intelligence",
    };
    document.title = titles[location.pathname] ?? "RAG Document Intelligence";
    // Do not steal focus on first paint; only on subsequent navigations.
    if (location.key !== "default") {
      main.focus({ preventScroll: true });
    }
  }, [location.pathname, location.key]);

  return <span className="visually-hidden" role="status" aria-live="polite" />;
}

function Shell() {
  const { motionEnabled } = useApp();

  return (
    <>
      <GalaxyBackground motionEnabled={motionEnabled} />
      <Layout>
        <RouteAnnouncer />
        <Routes>
          <Route path="/" element={<WelcomePage />} />
          <Route path="/documents" element={<DocumentsPage />} />
          <Route path="/processing" element={<ProcessingPage />} />
          <Route path="/processing/:id" element={<ProcessingPage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/evaluation" element={<EvaluationPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/workspace" element={<Navigate to="/documents" replace />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </Layout>
    </>
  );
}

export function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <AppProvider>
          <Shell />
        </AppProvider>
      </BrowserRouter>
    </ErrorBoundary>
  );
}

export default App;
