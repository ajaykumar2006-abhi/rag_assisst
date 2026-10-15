import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useAsync } from "@/hooks/useAsync";
import { useMutation } from "@/hooks/useMutation";
import { usePolling } from "@/hooks/usePolling";
import { ApiError } from "@/services/client";

describe("useAsync", () => {
  it("loads data and clears the loading flag", async () => {
    const { result } = renderHook(() => useAsync(async () => "value", []));

    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.data).toBe("value"));
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("exposes a typed ApiError when the loader rejects", async () => {
    const { result } = renderHook(() =>
      useAsync(async () => {
        throw new ApiError("Nope", { code: "validation_error", status: 422 });
      }, []),
    );

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error?.code).toBe("validation_error");
    expect(result.current.data).toBeNull();
  });

  it("does not fetch while disabled", async () => {
    const loader = vi.fn(async () => "x");
    const { result } = renderHook(() => useAsync(loader, [], { enabled: false }));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(loader).not.toHaveBeenCalled();
  });
});

describe("useMutation", () => {
  it("returns the result and reports pending state", async () => {
    const mutation = renderHook(() => useMutation(async (value: number) => value * 2));
    let output: number | null = null;

    await act(async () => {
      output = await mutation.result.current.run(21);
    });

    expect(output).toBe(42);
    expect(mutation.result.current.data).toBe(42);
    expect(mutation.result.current.pending).toBe(false);
  });

  it("captures the failure as an ApiError instead of throwing", async () => {
    const mutation = renderHook(() =>
      useMutation(async () => {
        throw new ApiError("Bad file", { code: "unsupported_type", status: 415 });
      }),
    );

    await act(async () => {
      await mutation.result.current.run();
    });

    expect(mutation.result.current.error?.code).toBe("unsupported_type");
  });

  it("ignores a second call while the first is still in flight", async () => {
    let resolveFirst: ((value: string) => void) | null = null;
    const fn = vi.fn(
      () =>
        new Promise<string>((resolve) => {
          resolveFirst = resolve;
        }),
    );
    const mutation = renderHook(() => useMutation(fn));

    let pending: Promise<string | null> | undefined;
    act(() => {
      pending = mutation.result.current.run();
    });
    await act(async () => {
      const second = await mutation.result.current.run();
      expect(second).toBeNull();
    });

    await act(async () => {
      resolveFirst?.("first");
      await pending;
    });

    expect(fn).toHaveBeenCalledTimes(1);
  });
});

describe("usePolling", () => {
  it("polls repeatedly and stops once stopWhen matches", async () => {
    const fn = vi.fn(async () => "settled");
    const { result } = renderHook(() => usePolling(fn, { intervalMs: 20, stopWhen: (value) => value === "settled" }));

    await waitFor(() => expect(result.current.value).toBe("settled"));
    await waitFor(() => expect(result.current.stopped).toBe(true));

    const callsWhenStopped = fn.mock.calls.length;
    await new Promise((resolve) => setTimeout(resolve, 120));
    // At most one extra tick is allowed while the effect settles.
    expect(fn.mock.calls.length).toBeLessThanOrEqual(callsWhenStopped + 1);
  });

  it("keeps polling while the stop condition is false", async () => {
    const fn = vi.fn(async () => "busy");
    const { result } = renderHook(() => usePolling(fn, { intervalMs: 20, stopWhen: () => false }));

    await waitFor(() => expect(result.current.value).toBe("busy"));
    await waitFor(() => expect(fn.mock.calls.length).toBeGreaterThanOrEqual(3), { timeout: 2000 });
  });

  it("runs the first request even in a hidden tab, then pauses until the tab is visible", async () => {
    const original = Object.getOwnPropertyDescriptor(document, "hidden");
    Object.defineProperty(document, "hidden", { configurable: true, get: () => true });

    try {
      const fn = vi.fn(async () => "hidden-value");
      const { result } = renderHook(() => usePolling(fn, { intervalMs: 20 }));

      // The first tick must still reach the backend, otherwise a page opened in a
      // background tab renders "nothing here" instead of the real records.
      await waitFor(() => expect(result.current.value).toBe("hidden-value"));
      expect(fn).toHaveBeenCalledTimes(1);

      await new Promise((resolve) => setTimeout(resolve, 120));
      expect(fn).toHaveBeenCalledTimes(1);
    } finally {
      if (original) {
        Object.defineProperty(document, "hidden", original);
      } else {
        delete (document as unknown as Record<string, unknown>).hidden;
      }
    }
  });

  it("records the error and backs off rather than hammering the backend", async () => {
    const fn = vi.fn(async () => {
      throw new Error("offline");
    });
    const { result } = renderHook(() => usePolling(fn, { intervalMs: 20, backoffFactor: 2, maxIntervalMs: 200 }));

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(fn.mock.calls.length).toBeLessThan(5);
  });
});
