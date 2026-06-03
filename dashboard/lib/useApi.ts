"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ApiResult, DataSource } from "./api";

export interface UseApiState<T> {
  data: T | null;
  source: DataSource | null;
  loading: boolean;
  error?: string;
  /** Re-run the fetch (e.g. a manual refresh button). */
  refresh: () => void;
}

/**
 * Minimal data hook over the resilient api client. The client never throws (it
 * falls back to mock data), so this only tracks loading + which source served
 * the data. `refresh` is stable; the fetch runs once on mount.
 */
export function useApiResource<T>(fetcher: () => Promise<ApiResult<T>>): UseApiState<T> {
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const [state, setState] = useState<Omit<UseApiState<T>, "refresh">>({
    data: null,
    source: null,
    loading: true,
  });

  const refresh = useCallback(() => {
    setState((s) => ({ ...s, loading: true }));
    fetcherRef
      .current()
      .then((res) => setState({ data: res.data, source: res.source, loading: false, error: res.error }))
      .catch((err) => setState((s) => ({ ...s, loading: false, error: String(err) })));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { ...state, refresh };
}
