import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./api";

export interface AsyncState<T> {
  data: T | null; error: ApiError | null; loading: boolean; reload: () => void;
}

/** Fetch on mount and whenever `deps` change. A null `fn` means "nothing to load yet". */
export function useAsync<T>(fn: (() => Promise<T>) | null, deps: unknown[]): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState<boolean>(fn !== null);
  const [tick, setTick] = useState(0);
  const seq = useRef(0);
  useEffect(() => {
    if (!fn) { setLoading(false); return; }
    const mine = ++seq.current;
    setLoading(true);
    fn().then(
      (d) => { if (seq.current === mine) { setData(d); setError(null); setLoading(false); } },
      (e) => { if (seq.current === mine) { setError(e instanceof ApiError ? e : new ApiError(0, "error", String(e))); setData(null); setLoading(false); } },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload };
}

/** Call `fn` every `ms` while `active` is true. */
export function usePolling(fn: () => void, ms: number, active: boolean) {
  const saved = useRef(fn);
  saved.current = fn;
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => saved.current(), ms);
    return () => clearInterval(id);
  }, [ms, active]);
}
