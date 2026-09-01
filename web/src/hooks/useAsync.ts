/**
 * Loading, error and data, in one hook.
 *
 * Every page that fetches uses this, so no page can accidentally forget its
 * loading state or swallow an error.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/api/client";

export interface AsyncState<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  reload: () => void;
}

export function useAsync<T>(
  fn: () => Promise<T>,
  deps: unknown[] = []
): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);
  const latest = useRef(0);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    const ticket = ++latest.current;
    setLoading(true);
    setError(null);
    fn()
      .then((value) => {
        if (ticket === latest.current) {
          setData(value);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (ticket !== latest.current) return;
        setError(
          err instanceof ApiError
            ? err
            : new ApiError(0, {
                message:
                  err instanceof Error ? err.message : "Something went wrong.",
              })
        );
        setLoading(false);
      });
    // The dependency list is supplied by the caller on purpose: it decides
    // when the request should run again.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  return { data, error, loading, reload };
}
