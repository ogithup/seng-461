import { useCallback, useEffect, useState } from "react";
import { describeError } from "../services/errors";
import type { AgentApi } from "../services/types";

export type PreviewState =
  | { status: "empty" }
  | { status: "loading" }
  // `version` changes on every successful check, so the iframe reloads changed files.
  | { status: "ready"; url: string; version: number }
  | { status: "error"; message: string };

/**
 * The generated site's preview (GET /api/preview). It is checked again whenever `stamp`
 * changes, but not while the agent is still writing files (`paused`), so the frame doesn't
 * reload on every task.
 */
export function usePreview(api: AgentApi, projectId: number | null, stamp: string, paused: boolean) {
  const [preview, setPreview] = useState<PreviewState>({ status: "loading" });
  const [reloads, setReloads] = useState(0);

  // A null id means the project's state hasn't loaded yet, so that is "loading" too.
  useEffect(() => {
    setPreview({ status: "loading" });
  }, [projectId]);

  useEffect(() => {
    if (projectId === null || paused) return;
    let cancelled = false;
    // Background checks keep what is on screen; only a retry after an error shows "loading".
    setPreview((p) => (p.status === "error" ? { status: "loading" } : p));
    api.getPreview(projectId).then(
      (info) => {
        if (cancelled) return;
        setPreview((p) =>
          info.status === "static" && info.url
            ? { status: "ready", url: info.url, version: p.status === "ready" ? p.version + 1 : 1 }
            : { status: "empty" },
        );
      },
      (err) => {
        if (!cancelled) setPreview({ status: "error", message: describeError(err) });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, projectId, stamp, paused, reloads]);

  const reload = useCallback(() => setReloads((n) => n + 1), []);

  return { preview, reload };
}
