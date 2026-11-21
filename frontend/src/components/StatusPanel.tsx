import type { LogEntry, ProjectState, RunStatus, TaskStatus } from "../services/types";
import { displayPrompt } from "../utils/format";
import { failureReason, type RequestRecord, type RequestSummary } from "../utils/requestSummary";
import { ApprovalCard } from "./ApprovalCard";

const RUN_LABEL: Record<RunStatus, string> = {
  idle: "Idle",
  running: "Running",
  waiting_for_approval: "Awaiting approval",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

export const TASK_LABEL: Record<TaskStatus, string> = {
  pending: "Pending",
  running: "Running",
  waiting_for_approval: "Awaiting approval",
  succeeded: "Succeeded",
  failed: "Failed",
  skipped: "Skipped",
  cancelled: "Cancelled",
};

// A status outside the contract is shown as it is, never as one of ours.
const label = (labels: Record<string, string>, status: string) =>
  Object.prototype.hasOwnProperty.call(labels, status) ? labels[status] : `Unknown (${status})`;

interface Props {
  state: ProjectState | null;
  /** The latest request sent from this browser, and what the backend's answers say about it. */
  request: RequestRecord | null;
  summary: RequestSummary | null;
  logs: LogEntry[];
  deciding: boolean;
  /** The last background status check failed. */
  syncError: string | null;
  onApprove: () => void;
  onReject: () => void;
}

/** The latest request's outcome, the project's status, every task, and any pending approval. */
export function StatusPanel({ state, request, summary, logs, deciding, syncError, onApprove, onReject }: Props) {
  const tasks = state?.tasks ?? [];
  const done = tasks.filter((t) => t.status === "succeeded").length;
  const failed = tasks.filter((t) => t.status === "failed").length;
  const inRequest = (id: number) => request !== null && request.phase !== "refused" && id > request.afterTaskId;

  return (
    <section className="card status-panel" aria-label="Agent status">
      <h2>Status</h2>

      {request && summary && <RequestResult text={request.text} summary={summary} />}

      <div className="status-line">
        <span className="muted">Project</span>
        {state ? (
          <span className={`badge run-${state.status}`} data-testid="run-status">
            {label(RUN_LABEL, state.status)}
          </span>
        ) : (
          <span className="badge" data-testid="run-status">
            Loading…
          </span>
        )}
        {tasks.length > 0 && (
          <span className="muted">
            {done}/{tasks.length} tasks done
            {failed > 0 && ` · ${failed} failed`}
          </span>
        )}
      </div>
      {syncError && (
        <p className="sync-error" role="status">
          Status updates paused: {syncError} Retrying…
        </p>
      )}

      {state?.pending_action && (
        <ApprovalCard
          action={state.pending_action}
          busy={deciding}
          onApprove={onApprove}
          onReject={onReject}
        />
      )}
      {!request && state?.status === "failed" && (
        <div className="notice notice-bad" role="status">
          The last run stopped after a failure. The failed task and the execution log show why.
        </div>
      )}

      <h3>Tasks</h3>
      {!state ? (
        <p className="muted">Loading tasks…</p>
      ) : tasks.length === 0 ? (
        <p className="muted">No tasks yet.</p>
      ) : (
        <ol className="task-list">
          {tasks.map((t) => (
            <li
              key={t.id}
              className={`task${inRequest(t.id) ? " task-current" : ""}`}
              data-status={t.status}
            >
              <span className="task-prompt" title={t.prompt}>
                {displayPrompt(t.prompt)}
              </span>
              <span className={`badge task-badge task-${t.status}`}>{label(TASK_LABEL, t.status)}</span>
              {t.status === "failed" && (
                <p className="task-reason">{failureReason(t.id, logs) ?? "No error details were recorded for this task."}</p>
              )}
              {t.status === "skipped" && <p className="task-note muted">Not run because an earlier task failed.</p>}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function RequestResult({ text, summary }: { text: string; summary: RequestSummary }) {
  const inProgress = summary.kind === "pending" || summary.kind === "running";
  return (
    <div className={`request request-${summary.kind}`} role="status" aria-label="Latest request">
      <div className="request-head">
        <span className="muted">Latest request</span>
        <span className={`badge req-${summary.kind}`} data-testid="request-status">
          {inProgress && <span className="spinner" aria-hidden="true" />}
          {summary.label}
        </span>
      </div>
      <p className="request-text">“{text}”</p>
      {inProgress &&
        (summary.total > 0 ? (
          <progress max={summary.total} value={summary.done} aria-label="Generation progress" />
        ) : (
          <progress aria-label="Generation progress" />
        ))}
      <p className="request-detail">{summary.detail}</p>
    </div>
  );
}
