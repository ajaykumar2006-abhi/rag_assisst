import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/services/client";

export interface AsyncState<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  /** True while a reload is in flight but previous data is still displayed. */
  refreshing: boolean;
  reload: () => void;
  setData: (updater: T | ((previous: T | null) => T | null)) => void;
}

function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  return new ApiError(error instanceof Error ? error.message : String(error), {
    code: "unexpected_error",
  });
}

/**
 * Run an async function and expose loading/error/data.
 *
 * Cancellation is wired to component unmount so a slow request cannot set state
 * on an unmounted component, and a newer call always wins over an older one.
 */
export function useAsync<T>(
  fn: (signal: AbortSignal) => Promise<T>,
  deps: unknown[],
  options: { enabled?: boolean; keepPreviousData?: boolean } = {},
): AsyncState<T> {
  const { enabled = true, keepPreviousData = true } = options;

  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState<boolean>(enabled);
  const [refreshing, setRefreshing] = useState(false);
  const [nonce, setNonce] = useState(0);

  const fnRef = useRef(fn);
  fnRef.current = fn;
  const hasDataRef = useRef(false);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }

    const controller = new AbortController();
    let active = true;
    const hadData = keepPreviousData && hasDataRef.current;
    setLoading(!hadData);
    setRefreshing(hadData);

    fnRef
      .current(controller.signal)
      .then((result) => {
        if (!active) return;
        setData(result);
        hasDataRef.current = true;
        setError(null);
      })
      .catch((caught: unknown) => {
        if (!active) return;
        const apiError = toApiError(caught);
        if (apiError.code === "cancelled") return;
        setError(apiError);
      })
      .finally(() => {
        if (!active) return;
        setLoading(false);
        setRefreshing(false);
      });

    return () => {
      active = false;
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, nonce, ...deps]);

  const reload = useCallback(() => setNonce((value) => value + 1), []);

  const update = useCallback((updater: T | ((previous: T | null) => T | null)) => {
    setData((previous) =>
      typeof updater === "function" ? (updater as (p: T | null) => T | null)(previous) : updater,
    );
  }, []);

  return { data, error, loading, refreshing, reload, setData: update };
}
