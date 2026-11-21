import type { LogEntry, ProjectState, Task } from "../services/types";
import { displayPrompt } from "./format";

/**
 * The latest request the user sent to a project, as far as this browser knows. The API has no
 * request id, but it numbers tasks in order and a request only ever appends tasks, so the tasks
 * with an id above `afterTaskId` are this request's (docs/sprint4-contracts.md §6).
 */
export interface RequestRecord {
  text: string;
  afterTaskId: number;
  /**
   * sending:     POST /chat is in flight.
   * answered:    the backend answered it.
   * refused:     the backend answered that it did not carry it out (4xx, or 502 from planning);
   *              no task was created, so later tasks are not attributed to it.
   * interrupted: no answer (network, timeout, 500); it may or may not have been applied, so the
   *              tasks GET /tasks shows afterwards are the only evidence.
   */
  phase: "sending" | "answered" | "refused" | "interrupted";
  error?: string;
}

export type RequestKind =
  | "pending"
  | "running"
  | "waiting"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "interrupted"
  | "unknown";

export interface RequestSummary {
  kind: RequestKind;
  /** Badge text. */
  label: string;
  /** One sentence under the badge. */
  detail: string;
  /** This request's tasks that succeeded, and all of its tasks. */
  done: number;
  total: number;
}

const KNOWN = new Set(["pending", "running", "waiting_for_approval", "succeeded", "failed", "skipped", "cancelled"]);

/** The backend's own explanation for a failed task: the output of its last failed action. */
export function failureReason(taskId: number, logs: LogEntry[]): string | null {
  for (let i = logs.length - 1; i >= 0; i--) {
    const e = logs[i];
    if (e.task_id !== taskId || e.status !== "failed") continue;
    const text = (e.stderr || e.stdout).trim();
    if (text) return text.length > 300 ? `${text.slice(0, 300)}…` : text;
  }
  return null;
}

/**
 * What happened to the latest request, derived only from what the backend reported. Success is
 * shown only when every one of the request's tasks is `succeeded` and either the backend has
 * answered POST /chat or reports the project `completed`.
 */
export function summarizeRequest(
  request: RequestRecord,
  state: ProjectState | null,
  logs: LogEntry[],
): RequestSummary {
  const summary = (kind: RequestKind, label: string, detail: string, tasks: Task[] = []) => ({
    kind,
    label,
    detail,
    done: tasks.filter((t) => t.status === "succeeded").length,
    total: tasks.length,
  });

  if (request.phase === "refused") {
    return summary("failed", "Failed", request.error ?? "The backend did not carry out this request.");
  }

  const tasks = (state?.tasks ?? []).filter((t) => t.id > request.afterTaskId);
  if (tasks.length === 0) {
    if (request.phase === "sending") {
      return summary("pending", "Pending", "Sent. Waiting for the backend to plan the request…");
    }
    if (request.phase === "interrupted") {
      return summary(
        "interrupted",
        "Interrupted",
        `${request.error ?? "The connection was lost."} The backend has not confirmed this request.`,
      );
    }
    return summary("unknown", "Unknown", "The backend answered but created no tasks for this request.");
  }

  const count = (status: string) => tasks.filter((t) => t.status === status).length;
  const strange = tasks.find((t) => !KNOWN.has(t.status));
  const failed = tasks.find((t) => t.status === "failed");

  if (failed) {
    const reason = failureReason(failed.id, logs);
    const skipped = count("skipped");
    return summary(
      "failed",
      "Failed",
      `“${displayPrompt(failed.prompt)}” failed: ${reason ?? "no error details were recorded."}` +
        (skipped ? ` ${skipped} later task(s) were skipped.` : ""),
      tasks,
    );
  }
  if (strange) {
    return summary("unknown", "Unknown", `The backend reported an unrecognised task status “${strange.status}”.`, tasks);
  }
  if (count("waiting_for_approval")) {
    return summary("waiting", "Awaiting approval", "A command needs your approval before the work can go on.", tasks);
  }
  if (count("running") || count("pending")) {
    const done = count("succeeded");
    return count("running")
      ? summary("running", "Running", `${done} of ${tasks.length} task(s) done…`, tasks)
      : summary("pending", "Pending", `${tasks.length} task(s) planned, waiting to start…`, tasks);
  }
  if (count("skipped")) {
    return summary("failed", "Failed", `${count("skipped")} task(s) were skipped after a failure.`, tasks);
  }
  if (count("cancelled")) {
    return summary("cancelled", "Cancelled", "The request was cancelled before it finished.", tasks);
  }
  // Every task succeeded. While POST /chat is still open, wait for the project's own verdict.
  if (request.phase === "sending" && state?.status !== "completed") {
    return summary("running", "Running", `${tasks.length} of ${tasks.length} task(s) done, finishing…`, tasks);
  }
  return summary("succeeded", "Succeeded", `All ${tasks.length} task(s) succeeded.`, tasks);
}

/** The highest task id in the state: the next request's tasks will be numbered above it. */
export function lastTaskId(state: ProjectState | null): number {
  return (state?.tasks ?? []).reduce((max, t) => Math.max(max, t.id), 0);
}
