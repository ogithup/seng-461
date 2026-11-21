import { useCallback, useEffect, useState } from "react";
import { describeError } from "../services/errors";
import type { AgentApi } from "../services/types";

export type Health =
  | { status: "checking" }
  | { status: "ok" }
  | { status: "down"; message: string };

/** GET /api/health once on load (and on demand), for the connection badge in the top bar. */
export function useBackendHealth(api: AgentApi) {
  const [health, setHealth] = useState<Health>({ status: "checking" });
  const [checks, setChecks] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setHealth({ status: "checking" });
    api.health().then(
      (res) => {
        if (cancelled) return;
        setHealth(res.status === "ok" ? { status: "ok" } : { status: "down", message: `Health check said “${res.status}”.` });
      },
      (err) => {
        if (!cancelled) setHealth({ status: "down", message: describeError(err) });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, checks]);

  const recheck = useCallback(() => setChecks((n) => n + 1), []);
  return { health, recheck };
}
