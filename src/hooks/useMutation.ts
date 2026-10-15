import { useCallback, useRef, useState } from "react";

import { ApiError } from "@/services/client";

export interface MutationState<TResult, TInput> {
  run: (input: TInput) => Promise<TResult | null>;
  data: TResult | null;
  error: ApiError | null;
  pending: boolean;
  reset: () => void;
}

/**
 * Wrap a write operation.
 *
 * While a call is in flight `pending` is true and further calls are ignored, which
 * is what stops a double-click from uploading a document twice. Errors are
 * returned (never swallowed) so the caller can show the real message.
 */
export function useMutation<TResult, TInput = void>(
  fn: (input: TInput) => Promise<TResult>,
  options: { onSuccess?: (result: TResult, input: TInput) => void; onError?: (error: ApiError) => void } = {},
): MutationState<TResult, TInput> {
  const [data, setData] = useState<TResult | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [pending, setPending] = useState(false);
  const inFlight = useRef(false);
  const mounted = useRef(true);

  const fnRef = useRef(fn);
  fnRef.current = fn;
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const run = useCallback(async (input: TInput): Promise<TResult | null> => {
    if (inFlight.current) return null;
    inFlight.current = true;
    setPending(true);
    setError(null);
    try {
      const result = await fnRef.current(input);
      if (mounted.current) {
        setData(result);
        optionsRef.current.onSuccess?.(result, input);
      }
      return result;
    } catch (caught) {
      const apiError =
        caught instanceof ApiError
          ? caught
          : new ApiError(caught instanceof Error ? caught.message : String(caught), {
              code: "unexpected_error",
            });
      if (mounted.current) {
        setError(apiError);
        optionsRef.current.onError?.(apiError);
      }
      return null;
    } finally {
      inFlight.current = false;
      if (mounted.current) setPending(false);
    }
  }, []);

  const reset = useCallback(() => {
    setData(null);
    setError(null);
  }, []);

  return { run, data, error, pending, reset };
}
