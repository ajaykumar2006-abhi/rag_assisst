import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { usePolling } from "@/hooks/usePolling";
import { useReducedMotion } from "@/hooks/useReducedMotion";
import { api, type ApiSurface } from "@/services/api";
import type { ApiError } from "@/services/client";
import type { HealthResponse } from "@/types/api";

export type ToastTone = "info" | "success" | "error";

export interface Toast {
  id: string;
  tone: ToastTone;
  title: string;
  message?: string;
  /** When set, the toast offers a retry action. */
  retry?: (() => void) | undefined;
}

export interface AppContextValue {
  api: ApiSurface;
  health: HealthResponse | null;
  healthError: ApiError | null;
  healthLoading: boolean;
  backendOnline: boolean;
  refreshHealth: () => void;
  toasts: Toast[];
  pushToast: (toast: Omit<Toast, "id">) => void;
  dismissToast: (id: string) => void;
  motionEnabled: boolean;
  toggleMotion: () => void;
  systemReducedMotion: boolean;
}

const AppContext = createContext<AppContextValue | null>(null);

const MOTION_STORAGE_KEY = "rag.motion-enabled";

function readStoredMotionPreference(): boolean | null {
  try {
    const raw = window.localStorage.getItem(MOTION_STORAGE_KEY);
    if (raw === null) return null;
    return raw === "true";
  } catch {
    return null;
  }
}

export function AppProvider({
  children,
  apiSurface = api,
}: {
  children: ReactNode;
  apiSurface?: ApiSurface;
}) {
  const systemReducedMotion = useReducedMotion();
  const [motionOverride, setMotionOverride] = useState<boolean | null>(() =>
    typeof window === "undefined" ? null : readStoredMotionPreference(),
  );
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [healthNonce, setHealthNonce] = useState(0);

  // The health signal drives the sidebar indicator and the Settings screen.
  const {
    value: health,
    error: pollError,
  } = usePolling<HealthResponse>(() => apiSurface.health(), {
    intervalMs: 15_000,
    refreshKey: healthNonce,
  });

  const [healthError, setHealthError] = useState<ApiError | null>(null);
  useEffect(() => {
    setHealthError((pollError as ApiError) ?? null);
  }, [pollError]);

  const pushToast = useCallback((toast: Omit<Toast, "id">) => {
    const id = `toast_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    setToasts((current) => [...current.slice(-3), { ...toast, id }]);
    if (toast.tone !== "error") {
      setTimeout(() => setToasts((current) => current.filter((item) => item.id !== id)), 6000);
    }
  }, []);

  const dismissToast = useCallback((id: string) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const toggleMotion = useCallback(() => {
    setMotionOverride((current) => {
      const next = !(current ?? !systemReducedMotion);
      try {
        window.localStorage.setItem(MOTION_STORAGE_KEY, String(next));
      } catch {
        /* storage unavailable (private mode) — the in-memory value still applies */
      }
      return next;
    });
  }, [systemReducedMotion]);

  const value = useMemo<AppContextValue>(() => {
    const motionEnabled = motionOverride ?? !systemReducedMotion;
    return {
      api: apiSurface,
      health,
      healthError,
      healthLoading: health === null && healthError === null,
      backendOnline: health !== null && health.status === "ok",
      refreshHealth: () => setHealthNonce((n) => n + 1),
      toasts,
      pushToast,
      dismissToast,
      motionEnabled,
      toggleMotion,
      systemReducedMotion,
    };
  }, [
    apiSurface,
    health,
    healthError,
    toasts,
    pushToast,
    dismissToast,
    motionOverride,
    systemReducedMotion,
    toggleMotion,
  ]);

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error("useApp must be used inside an <AppProvider>.");
  }
  return context;
}
