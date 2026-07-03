/*
 * SSE consumers for the platform's two live text/event-stream endpoints:
 * instance provisioning logs and sandbox detonation events.
 *
 * EventSource cannot send the Authorization header, so streams are read with
 * fetch() and parsed by hand — the format is plain text/event-stream:
 * `data: {json}` frames for payload rows and one final `event: state` frame
 * when the run settles (docs/ephemeral-lifecycle.md §3).
 */

import { API_ORIGIN, type ApiPath, readToken } from "./client";
import type { InstanceLogOut, InstanceState, SandboxEventOut } from "./types";

type SSEHandlers<T> = {
  onData: (row: T) => void;
  /** Fired once with the settled state right before the stream closes. */
  onState?: (state: string) => void;
  onError?: (err: Error) => void;
};

/** Core reader: follows an authenticated SSE endpoint. Returns an abort fn. */
function streamSSE<T>(path: ApiPath, handlers: SSEHandlers<T>): () => void {
  const controller = new AbortController();

  (async () => {
    const headers: Record<string, string> = { Accept: "text/event-stream" };
    const token = readToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    let resp: Response;
    try {
      resp = await fetch(`${API_ORIGIN}${path}`, {
        headers,
        signal: controller.signal,
      });
    } catch (err) {
      if (!controller.signal.aborted)
        handlers.onError?.(err instanceof Error ? err : new Error(String(err)));
      return;
    }
    if (!resp.ok || !resp.body) {
      handlers.onError?.(new Error(`stream failed (${resp.status})`));
      return;
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let eventName = "message";
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let nl: number;
        while ((nl = buffer.indexOf("\n")) !== -1) {
          const raw = buffer.slice(0, nl).replace(/\r$/, "");
          buffer = buffer.slice(nl + 1);
          if (raw === "") {
            eventName = "message"; // frame boundary resets the event type
            continue;
          }
          if (raw.startsWith("event:")) {
            eventName = raw.slice(6).trim();
            continue;
          }
          if (!raw.startsWith("data:")) continue;
          const data = raw.slice(5).trim();
          if (eventName === "state") {
            handlers.onState?.(data);
          } else {
            try {
              handlers.onData(JSON.parse(data) as T);
            } catch {
              /* skip malformed frames */
            }
          }
        }
      }
    } catch (err) {
      if (!controller.signal.aborted)
        handlers.onError?.(err instanceof Error ? err : new Error(String(err)));
    }
  })();

  return () => controller.abort();
}

export type LogStreamHandlers = {
  onLine: (line: InstanceLogOut) => void;
  onState?: (state: InstanceState | "unknown") => void;
  onError?: (err: Error) => void;
};

/** Follows an instance's provisioning log. Returns an abort function. */
export function streamInstanceLogs(
  instanceId: string,
  handlers: LogStreamHandlers
): () => void {
  return streamSSE<InstanceLogOut>(
    `/api/v1/instances/${instanceId}/logs/stream`,
    {
      onData: handlers.onLine,
      onState: (s) => handlers.onState?.(s as InstanceState | "unknown"),
      onError: handlers.onError,
    }
  );
}

export type SandboxStreamHandlers = {
  onEvent: (event: SandboxEventOut) => void;
  onState?: (state: string) => void;
  onError?: (err: Error) => void;
};

/** Follows a sandbox report's detonation event trace. Returns an abort fn. */
export function streamSandboxEvents(
  reportId: string,
  handlers: SandboxStreamHandlers
): () => void {
  return streamSSE<SandboxEventOut>(
    `/api/v1/sandbox/reports/${reportId}/events/stream`,
    {
      onData: handlers.onEvent,
      onState: handlers.onState,
      onError: handlers.onError,
    }
  );
}
