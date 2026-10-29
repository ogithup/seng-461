import type { ProjectState, RunStatus, TaskStatus } from "../services/types";
import { ApprovalCard } from "./ApprovalCard";

const RUN_LABEL: Record<RunStatus, string> = {
  idle: "Idle",
  running: "Working",
  waiting_for_approval: "Awaiting approval",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

export const TASK_LABEL: Record<TaskStatus, string> = {
  pending: "Pending",
  running: "Running",
  waiting_for_approval: "Awaiting approval",
  succeeded: "Completed",
  failed: "Failed",
  skipped: "Skipped",
  cancelled: "Cancelled",
};

interface Props {
  state: ProjectState | null;
  sending: boolean;
  deciding: boolean;
  onApprove: () => void;
  onReject: () => void;
}

/** Whether the agent is working, finished or stuck; every task; and any pending approval. */
export function StatusPanel({ state, sending, deciding, onApprove, onReject }: Props) {
  const status: RunStatus = sending ? "running" : state?.status ?? "idle";
  const tasks = state?.tasks ?? [];
  const done = tasks.filter((t) => t.status === "succeeded").length;
  const failed = tasks.filter((t) => t.status === "failed").length;

  return (
    <section className="card status-panel" aria-label="Agent status">
      <h2>Status</h2>
      <div className="status-line">
        <span className={`badge run-${status}`} data-testid="run-status">
          {RUN_LABEL[status]}
        </span>
        {tasks.length > 0 && (
          <span className="muted">
            {done}/{tasks.length} tasks done
            {failed > 0 && ` · ${failed} failed`}
          </span>
        )}
      </div>

      {state?.pending_action && (
        <ApprovalCard
          action={state.pending_action}
          busy={deciding}
          onApprove={onApprove}
          onReject={onReject}
        />
      )}
      {!sending && state?.status === "failed" && (
        <div className="notice notice-bad" role="status">
          The run stopped after a failure. The execution log shows what went wrong.
        </div>
      )}

      <h3>Tasks</h3>
      {tasks.length === 0 ? (
        <p className="muted">No tasks yet.</p>
      ) : (
        <ol className="task-list">
          {tasks.map((t) => (
            <li key={t.id} className="task" data-status={t.status}>
              <span className="task-prompt">{t.prompt}</span>
              <span className={`badge task-badge task-${t.status}`}>{TASK_LABEL[t.status]}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
