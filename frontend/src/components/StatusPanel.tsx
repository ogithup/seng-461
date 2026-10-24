import type { ProjectState, RunStatus, TaskStatus } from "../services/types";

const RUN_LABEL: Record<RunStatus, string> = {
  idle: "Idle",
  running: "Working",
  waiting_for_approval: "Waiting for approval",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

const TASK_LABEL: Record<TaskStatus, string> = {
  pending: "Pending",
  running: "Running",
  waiting_for_approval: "Needs approval",
  succeeded: "Done",
  failed: "Failed",
  skipped: "Skipped",
  cancelled: "Cancelled",
};

interface Props {
  state: ProjectState | null;
  sending: boolean;
}

/** Shows whether the agent is working, finished or stuck, and every task in the project. */
export function StatusPanel({ state, sending }: Props) {
  const status: RunStatus = sending ? "running" : state?.status ?? "idle";
  const tasks = state?.tasks ?? [];
  const done = tasks.filter((t) => t.status === "succeeded").length;

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
          </span>
        )}
      </div>

      {state?.pending_action && (
        <div className="notice" role="status">
          A command is waiting for approval: <code>{state.pending_action.command}</code>
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
