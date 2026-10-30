import { useEffect, useRef, useState } from "react";
import { describeError } from "../services/errors";
import { MAX_LOG_PAGE, type AgentApi, type LogEntry } from "../services/types";

// Upper bound on pages read per refresh, so a huge log can't keep the UI fetching forever.
const MAX_PAGES = 20;

function mergeById(known: LogEntry[], fresh: LogEntry[]): LogEntry[] {
  const byId = new Map(known.map((e) => [e.id, e]));
  for (const entry of fresh) byId.set(entry.id, entry);
  return [...byId.values()].sort((a, b) => a.id - b.id);
}

/**
 * The project's execution log (GET /api/logs), refetched whenever `stamp` changes. Only newer
 * entries are requested, except that entries still awaiting approval are read again because
 * their status changes once a human decides.
 */
export function useExecutionLogs(api: AgentApi, projectId: number | null, stamp: string) {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const known = useRef<LogEntry[]>([]);

  useEffect(() => {
    known.current = [];
    setEntries([]);
    setError(null);
  }, [projectId]);

  useEffect(() => {
    if (projectId === null) return;
    let cancelled = false;

    async function load(id: number) {
      const open = known.current.find((e) => e.status === "pending_approval");
      const last = known.current[known.current.length - 1];
      let after = open ? open.id - 1 : last?.id ?? 0;
      const fresh: LogEntry[] = [];
      for (let page = 0; page < MAX_PAGES; page++) {
        const res = await api.getLogs(id, after, MAX_LOG_PAGE);
        fresh.push(...res.entries);
        if (res.entries.length < MAX_LOG_PAGE) break;
        after = res.next_after_id;
      }
      return fresh;
    }

    load(projectId).then(
      (fresh) => {
        if (cancelled) return;
        known.current = mergeById(known.current, fresh);
        setEntries(known.current);
        setError(null);
      },
      (err) => {
        if (!cancelled) setError(describeError(err));
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, projectId, stamp]);

  return { entries, error };
}
