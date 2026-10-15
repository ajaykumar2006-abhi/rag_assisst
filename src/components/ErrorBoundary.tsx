import { Component, type ErrorInfo, type ReactNode } from "react";

interface State {
  error: Error | null;
  componentStack: string | null;
}

/**
 * Catches render-time exceptions so a single broken screen cannot blank the app.
 *
 * The real message and component stack are shown (useful while developing) and
 * logged to the console; the user gets a Reload action rather than a white page.
 */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  override state: State = { error: null, componentStack: null };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo) {
    this.setState({ componentStack: info.componentStack ?? null });
    console.error("Unhandled UI error:", error, info.componentStack);
  }

  override render() {
    const { error, componentStack } = this.state;
    if (!error) return this.props.children;

    return (
      <div className="main__inner">
        <div className="error-state" role="alert">
          <h2>This screen hit an unexpected error</h2>
          <p>{error.message}</p>
          <p className="error-state__code">
            {error.name}
            {componentStack ? ` — ${componentStack.trim().split("\n")[0]}` : ""}
          </p>
          <div className="row" style={{ marginTop: 12 }}>
            <button type="button" className="btn btn--primary" onClick={() => window.location.assign("/")}>
              Back to the welcome screen
            </button>
            <button type="button" className="btn" onClick={() => window.location.reload()}>
              Reload the app
            </button>
          </div>
        </div>
      </div>
    );
  }
}
