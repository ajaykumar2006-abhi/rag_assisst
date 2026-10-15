import { useEffect, useRef, useState } from "react";

export interface PollingOptions<T = unknown> {
  /** Poll period in ms. */
  intervalMs?: number;
  /** Stop polling once this returns true (evaluated after each successful tick). */
  stopWhen?: (value: T) => boolean;
  enabled?: boolean;
  /** Multiplier applied to the interval after each consecutive failure. */
  backoffFactor?: number;
  maxIntervalMs?: number;
  /** Change this value to restart the polling loop immediately. */
  refreshKey?: number;
}

/**
 * Repeatedly call `fn` until `stopWhen` says to stop.
 *
 * Failures back off instead of hammering the backend, and repeated polling pauses
 * while the tab is hidden (the first call always runs, so a page mounted in a
 * background tab still shows real data instead of an empty state). The last
 * successful value plus any error are exposed so the UI can show real progress
 * rather than a decorative animation.
 */
export function usePolling<T>(
  fn: (signal: AbortSignal) => Promise<T>,
  {
    intervalMs = 1000,
    stopWhen,
    enabled = true,
    backoffFactor = 1.6,
    maxIntervalMs = 10_000,
    refreshKey = 0,
  }: PollingOptions<T> = {},
) {
  const [value, setValue] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [stopped, setStopped] = useState(false);

  const fnRef = useRef(fn);
  fnRef.current = fn;
  const stopRef = useRef(stopWhen);
  stopRef.current = stopWhen;

  useEffect(() => {
    if (!enabled) return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let delay = intervalMs;
    let controller: AbortController | null = null;
    // The very first request always runs: a page opened in a background tab must
    // still render its real data rather than the "nothing here" state.
    let ticked = false;

    const schedule = () => {
      if (cancelled) return;
      timer = setTimeout(tick, delay);
    };

    const tick = async () => {
      if (cancelled) return;
      const isFirstTick = !ticked;
      ticked = true;
      if (!isFirstTick && typeof document !== "undefined" && document.hidden) {
        schedule();
        return;
      }
      controller = new AbortController();
      try {
        const result = await fnRef.current(controller.signal);
        if (cancelled) return;
        setValue(result);
        setError(null);
        delay = intervalMs;
        if (stopRef.current?.(result)) {
          setStopped(true);
          return;
        }
      } catch (caught) {
        if (cancelled) return;
        setError(caught);
        delay = Math.min(delay * backoffFactor, maxIntervalMs);
      }
      schedule();
    };

    void tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      controller?.abort();
    };
  }, [enabled, intervalMs, backoffFactor, maxIntervalMs, stopped, refreshKey]);

  return { value, error, stopped, paused: enabled === false };
}
