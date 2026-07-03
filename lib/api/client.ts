/*
 * The frontend's single doorway to the core API (Phase 5).
 *
 * Base URL: NEXT_PUBLIC_PALESTRIX_API (an origin, no trailing slash),
 * defaulting to the development API at http://localhost:8000. Paths are
 * given in full ("/api/v1/...") so they read exactly like docs/public-api.md
 * and the plugin ScopedApi contract.
 *
 * Auth: the session bearer token lives in localStorage and rides in the
 * Authorization header — never in cookies, so CSRF has nothing to ride on.
 */

export const API_ORIGIN =
  process.env.NEXT_PUBLIC_PALESTRIX_API ?? "http://localhost:8000";

export type ApiPath = `/api/v1/${string}` | "/healthz";

const TOKEN_KEY = "palestrix.token";

export function readToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function writeToken(token: string) {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  window.localStorage.removeItem(TOKEN_KEY);
}

/** Structured API failure. `detail` keeps the backend's shape: a string for
 * plain errors, an object for machine-readable ones (quota_exceeded,
 * insufficient_palestras, cooldown). */
export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : apiErrorLabel(status, detail));
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }

  /** The backend's error code when the detail is structured, else null. */
  get code(): string | null {
    if (
      this.detail &&
      typeof this.detail === "object" &&
      "error" in this.detail
    ) {
      return String((this.detail as { error: unknown }).error);
    }
    return null;
  }
}

function apiErrorLabel(status: number, detail: unknown): string {
  const code =
    detail && typeof detail === "object" && "error" in detail
      ? String((detail as { error: unknown }).error)
      : null;
  switch (code) {
    case "quota_exceeded":
      return "Your tenant is at its instance quota. Destroy an instance first.";
    case "insufficient_palestras": {
      const d = detail as { cost?: number; balance?: number };
      return `Not enough Palestras: costs ${d.cost ?? "?"} P, you have ${d.balance ?? "?"} P.`;
    }
    case "cooldown": {
      const d = detail as { retry_after?: number };
      return `Cooldown active. Try again in ${d.retry_after ?? "a few"} seconds.`;
    }
    default:
      return `Request failed (${status}).`;
  }
}

async function request<T>(
  path: ApiPath,
  init: RequestInit = {}
): Promise<T> {
  const headers = new Headers(init.headers);
  const token = readToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && typeof init.body === "string") {
    headers.set("Content-Type", "application/json");
  }
  let resp: Response;
  try {
    resp = await fetch(`${API_ORIGIN}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "The API is unreachable. Is the backend running?");
  }
  if (!resp.ok) {
    let detail: unknown = resp.statusText;
    try {
      const body = await resp.json();
      detail = body?.detail ?? body;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(resp.status, detail);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

export const api = {
  get<T>(path: ApiPath): Promise<T> {
    return request<T>(path);
  },
  post<T>(path: ApiPath, body?: unknown): Promise<T> {
    return request<T>(path, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  },
  /** multipart/form-data POST (uploads, /labs/templates publishing). */
  postForm<T>(path: ApiPath, form: FormData): Promise<T> {
    return request<T>(path, { method: "POST", body: form });
  },
  del<T>(path: ApiPath): Promise<T> {
    return request<T>(path, { method: "DELETE" });
  },
};
