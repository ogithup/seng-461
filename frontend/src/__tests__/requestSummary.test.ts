import { describe, expect, it } from "vitest";
import type { LogEntry, ProjectState, Task } from "../services/types";
import { displayPrompt } from "../utils/format";
import { failureReason, lastTaskId, summarizeRequest, type RequestRecord } from "../utils/requestSummary";

const task = (id: number, status: string, prompt = `Write f${id}.html`) =>
  ({ id, project_id: 1, type: "step", status, prompt }) as Task;

const state = (status: string, tasks: Task[]) =>
  ({ project_id: 1, status, tasks, pending_action: null }) as ProjectState;

const log = (id: number, taskId: number, status: string, stderr = "", stdout = "") =>
  ({
    id, task_id: taskId, command: "write_file x", status, stdout, stderr,
    output_truncated: false, retry_count: 0, duration_ms: 1, reason: null, created_at: "",
  }) as LogEntry;

const req = (phase: RequestRecord["phase"], afterTaskId = 2, error?: string): RequestRecord => ({
  text: "Create a blog",
  afterTaskId,
  phase,
  error,
});

// Tasks 1-2 belong to an earlier request; this request's tasks are 3+.
const earlier = [task(1, "succeeded"), task(2, "failed")];

describe("summarizeRequest", () => {
  it("is Pending while the request is sent and the backend has created no task", () => {
    expect(summarizeRequest(req("sending"), state("completed", earlier), [])).toMatchObject({
      kind: "pending",
      label: "Pending",
      total: 0,
    });
  });

  it("is Pending while every task of the request is still pending", () => {
    const s = summarizeRequest(req("sending"), state("running", [...earlier, task(3, "pending"), task(4, "pending")]), []);
    expect(s).toMatchObject({ kind: "pending", done: 0, total: 2 });
  });

  it("is Running with progress, counting only this request's tasks", () => {
    const s = summarizeRequest(
      req("sending"),
      state("running", [...earlier, task(3, "succeeded"), task(4, "running"), task(5, "pending")]),
      [],
    );
    expect(s).toMatchObject({ kind: "running", label: "Running", done: 1, total: 3 });
    expect(s.detail).toBe("1 of 3 task(s) done…");
  });

  it("is Succeeded once every task succeeded and the backend answered", () => {
    const s = summarizeRequest(req("answered"), state("completed", [...earlier, task(3, "succeeded")]), []);
    expect(s).toMatchObject({ kind: "succeeded", label: "Succeeded", done: 1, total: 1 });
  });

  it("does not claim success during the request until the project is completed", () => {
    const tasks = [...earlier, task(3, "succeeded")];
    expect(summarizeRequest(req("sending"), state("running", tasks), []).kind).toBe("running");
    expect(summarizeRequest(req("sending"), state("completed", tasks), []).kind).toBe("succeeded");
  });

  it("is Failed with the backend's reason from the log", () => {
    const tasks = [...earlier, task(3, "succeeded"), task(4, "failed", "Write about.html"), task(5, "skipped")];
    const logs = [log(1, 2, "failed", "older failure"), log(2, 4, "failed", "File type '.exe' is not allowed.")];
    const s = summarizeRequest(req("answered"), state("failed", tasks), logs);
    expect(s).toMatchObject({ kind: "failed", label: "Failed", done: 1, total: 3 });
    expect(s.detail).toBe(
      "“Write about.html” failed: File type '.exe' is not allowed. 1 later task(s) were skipped.",
    );
  });

  it("says so when a failed task has no recorded reason", () => {
    const s = summarizeRequest(req("answered"), state("failed", [...earlier, task(3, "failed")]), []);
    expect(s.detail).toMatch(/no error details were recorded/);
  });

  it("is Failed with the backend's message when the request was refused, ignoring later tasks", () => {
    const msg = "Online shops are not supported yet. Try a blog, portfolio or landing page.";
    // Tasks 3+ could come from another tab's request; a refused request created none.
    const s = summarizeRequest(req("refused", 2, msg), state("running", [...earlier, task(3, "running")]), []);
    expect(s).toMatchObject({ kind: "failed", detail: msg, total: 0 });
  });

  it("is Interrupted when the answer was lost and the backend shows nothing for it", () => {
    const s = summarizeRequest(req("interrupted", 2, "Can't reach the backend."), state("completed", earlier), []);
    expect(s.kind).toBe("interrupted");
    expect(s.detail).toBe("Can't reach the backend. The backend has not confirmed this request.");
  });

  it("follows the backend's tasks when an interrupted request did run", () => {
    const s = summarizeRequest(req("interrupted"), state("completed", [...earlier, task(3, "succeeded")]), []);
    expect(s.kind).toBe("succeeded");
  });

  it("reports approval and cancellation", () => {
    expect(summarizeRequest(req("answered"), state("waiting_for_approval", [task(3, "waiting_for_approval")]), []).kind).toBe(
      "waiting",
    );
    expect(summarizeRequest(req("answered"), state("cancelled", [task(3, "cancelled")]), []).kind).toBe("cancelled");
  });

  it("never turns an unknown status into success", () => {
    const s = summarizeRequest(req("answered"), state("completed", [task(3, "succeeded"), task(4, "queued")]), []);
    expect(s).toMatchObject({ kind: "unknown", label: "Unknown" });
  });

  it("is Unknown if the backend answered without creating tasks", () => {
    expect(summarizeRequest(req("answered"), state("completed", earlier), []).kind).toBe("unknown");
  });
});

describe("failureReason", () => {
  it("uses the last failed action of the task, stderr first, then stdout", () => {
    const logs = [log(1, 3, "failed", "first"), log(2, 3, "succeeded"), log(3, 3, "failed", "", "only stdout")];
    expect(failureReason(3, logs)).toBe("only stdout");
    expect(failureReason(9, logs)).toBeNull();
  });

  it("shortens very long output", () => {
    const reason = failureReason(3, [log(1, 3, "failed", "x".repeat(1000))])!;
    expect(reason).toHaveLength(301);
    expect(reason.endsWith("…")).toBe(true);
  });
});

describe("helpers", () => {
  it("lastTaskId is the highest task id, or 0", () => {
    expect(lastTaskId(null)).toBe(0);
    expect(lastTaskId(state("idle", [task(4, "succeeded"), task(9, "failed"), task(7, "pending")]))).toBe(9);
  });

  it("displayPrompt hides only a trailing machine token", () => {
    expect(displayPrompt('Write a.html (blog site "X") [delta:eJyrVkrLz1eyUlAq]')).toBe('Write a.html (blog site "X")');
    expect(displayPrompt('Write a.html (blog site "X [draft]")')).toBe('Write a.html (blog site "X [draft]")');
    expect(displayPrompt("Write a.html")).toBe("Write a.html");
  });
});
