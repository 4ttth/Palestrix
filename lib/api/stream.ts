/*
 * SSE consumer for GET /api/v1/instances/{id}/logs/stream.
 *
 * EventSource cannot send the Authorization header, so the stream is read
 * with fetch() and parsed by hand — the format is plain text/event-stream:
 * `data: {json}` frames for log lines and one final `event: state` frame
 * when the instance settles (docs/ephemeral-lifecycle.md §3).
 */

import { API_ORIGIN, readToken } from "./client";
import type { InstanceLogOut, InstanceState } from "./types";

export type LogStreamHandlers = {
  onLine: (line: InstanceLogOut) => void;
  /** Fired once with the settled state right before the stream closes. */
  onState?: (state: InstanceState | "unknown") => void;
  onError?: (err: Error) => void;
};

/** Follows an instance's provisioning log. Returns an abort function. */
export function streamInstanceLogs(
  instanceId: string,
  handlers: LogStreamHandlers
): () => void {
  const controller = new AbortController();

  (async () => {
    const headers: Record<string, string> = { Accept: "text/event-stream" };
    const token = readToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    let resp: Response;
    try {
      resp = await fetch(
        `${API_ORIGIN}/api/v1/instances/${instanceId}/logs/stream`,
        { headers, signal: controller.signal }
      );
    } catch (err) {
      if (!controller.signal.aborted)
        handlers.onError?.(err instanceof Error ? err : new Error(String(err)));
      return;
    }
    if (!resp.ok || !resp.body) {
      handlers.onError?.(new Error(`log stream failed (${resp.status})`));
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
            handlers.onState?.(data as InstanceState | "unknown");
          } else {
            try {
              handlers.onLine(JSON.parse(data) as InstanceLogOut);
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
