"use client";

/*
 * useApi: the one data-fetching hook the live surfaces share. Deliberately
 * tiny (no cache, no dedupe) — each surface owns its data and refetches
 * after the mutations it performs. `path: null` skips fetching so calls can
 * be chained ("wait until the event id is known").
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, type ApiPath } from "./client";

export type Async<T> = {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  refetch: () => Promise<void>;
};

export function useApi<T>(path: ApiPath | null): Async<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(path !== null);
  const generation = useRef(0);

  const run = useCallback(async () => {
    if (path === null) return;
    const mine = ++generation.current;
    setLoading(true);
    try {
      const result = await api.get<T>(path);
      if (generation.current === mine) {
        setData(result);
        setError(null);
      }
    } catch (err) {
      if (generation.current === mine) {
        setError(
          err instanceof ApiError ? err : new ApiError(0, String(err))
        );
      }
    } finally {
      if (generation.current === mine) setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    if (path === null) {
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }
    void run();
  }, [path, run]);

  return { data, error, loading, refetch: run };
}
