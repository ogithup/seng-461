import type { ExecutionStatus, LogEntry } from "../services/types";
import { formatDuration, formatTime } from "../utils/format";

const EXEC_LABEL: Record<ExecutionStatus, string> = {
  pending_approval: "Awaiting approval",
  succeeded: "Succeeded",
  failed: "Failed",
  rejected: "Rejected",
  expired: "Expired",
};

interface Props {
  entries: LogEntry[];
  error: string | null;
}

/** Every action the system ran or asked to run, newest first, with its output. */
export function LogsPanel({ entries, error }: Props) {
  return (
    <section className="card logs-panel" aria-label="Execution log">
      <h2>Execution log</h2>
      {error && <p className="panel-error">Couldn't load the log: {error}</p>}
      {entries.length === 0 ? (
        <p className="muted">Nothing has run yet.</p>
      ) : (
        <ol className="log-list" reversed>
          {[...entries].reverse().map((e) => (
            <li key={e.id} className="log-entry" data-status={e.status}>
              <div className="log-head">
                <code className="log-command">{e.command}</code>
                <span className={`badge exec-${e.status}`}>{EXEC_LABEL[e.status]}</span>
                <span className="muted">
                  {formatTime(e.created_at)}
                  {e.status !== "pending_approval" && ` · ${formatDuration(e.duration_ms)}`}
                  {e.retry_count > 0 && ` · retried ${e.retry_count}×`}
                </span>
              </div>
              {e.reason && <p className="log-reason muted">{e.reason}</p>}
              {e.stdout && <pre className="log-out">{e.stdout}</pre>}
              {e.stderr && <pre className="log-out log-err">{e.stderr}</pre>}
              {e.output_truncated && <p className="muted">Output was truncated.</p>}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
