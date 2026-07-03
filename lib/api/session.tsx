"use client";

/*
 * Session context for the product shell. Wraps the (app) route group:
 * resolves the stored bearer token to a user via GET /auth/me, loads the
 * gamification summary for the topbar, and redirects to /login when the
 * token is missing or stale. Mutating surfaces call refreshSummary() after
 * anything that moves Palestras so the topbar never shows a stale balance.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { usePathname, useRouter } from "next/navigation";
import { api, ApiError, clearToken, readToken } from "./client";
import type { GamificationSummaryOut, UserOut } from "./types";

type Session = {
  user: UserOut;
  /** null while loading and for staff (staff have no earn path). */
  summary: GamificationSummaryOut | null;
  refreshSummary: () => Promise<void>;
  logout: () => void;
};

const SessionContext = createContext<Session | null>(null);

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useSession outside SessionProvider");
  return session;
}

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<UserOut | null>(null);
  const [summary, setSummary] = useState<GamificationSummaryOut | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  const toLogin = useCallback(() => {
    clearToken();
    const next = pathname ? `?next=${encodeURIComponent(pathname)}` : "";
    router.replace(`/login${next}`);
  }, [router, pathname]);

  const refreshSummary = useCallback(async () => {
    try {
      setSummary(await api.get<GamificationSummaryOut>("/api/v1/gamification/summary"));
    } catch {
      /* summary is decoration; the session survives without it */
    }
  }, []);

  useEffect(() => {
    if (!readToken()) {
      toLogin();
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const me = await api.get<UserOut>("/api/v1/auth/me");
        if (cancelled) return;
        setUser(me);
        void refreshSummary();
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) {
          toLogin();
        } else {
          setFailed(
            err instanceof ApiError && err.status === 0
              ? "The API is unreachable. Start the backend (uvicorn palestrix.main:app) and reload."
              : "Could not load your session. Reload to retry."
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [toLogin, refreshSummary]);

  const logout = useCallback(() => {
    clearToken();
    router.replace("/login");
  }, [router]);

  if (failed) {
    return (
      <div className="flex min-h-[100dvh] items-center justify-center p-6">
        <div className="max-w-md rounded-(--radius-card) border border-border bg-surface p-6 text-center">
          <p className="text-sm font-semibold tracking-tight">PalestrIX is offline</p>
          <p className="mt-2 text-[13px] leading-relaxed text-muted">{failed}</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div
        className="flex min-h-[100dvh] items-center justify-center"
        role="status"
        aria-label="Signing you in"
      >
        <p className="font-mono text-xs text-muted">checking session...</p>
      </div>
    );
  }

  return (
    <SessionContext.Provider value={{ user, summary, refreshSummary, logout }}>
      {children}
    </SessionContext.Provider>
  );
}
