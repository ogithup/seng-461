import { describe, expect, it } from "vitest";
import { createApi } from "../services";
import { MockAgentApi, classify, fakePlan } from "../services/mockApi";

describe("MockAgentApi (in-browser fake backend)", () => {
  it("classifies requests like backend/agent/planner.py", () => {
    expect(classify("Create a blog")).toEqual({ siteType: "blog", title: "My Blog" });
    expect(classify("Build my portfolio called Ada Lovelace!")).toEqual({
      siteType: "portfolio",
      title: "Ada Lovelace",
    });
    expect(classify("Make a site for <Acme>")).toEqual({ siteType: "landing", title: "Acme" });
  });

  it("plans one write step per file, index.html first, in the orchestrator's format", () => {
    expect(fakePlan("Create a blog")).toEqual([
      'Write index.html (blog site "My Blog")',
      'Write about.html (blog site "My Blog")',
      'Write style.css (blog site "My Blog")',
    ]);
    expect(fakePlan("A landing page")).toHaveLength(2);
  });

  it("runs the Sprint 3 flow: chat → tasks → files, logs and a preview", async () => {
    const api = new MockAgentApi(0);
    const project = await api.createProject("Blog");
    expect(project).toMatchObject({ id: 1, name: "Blog", session_id: 1 });
    expect((await api.getTasks(project.id)).status).toBe("idle");
    expect((await api.getPreview(project.id)).status).toBe("unavailable");

    const res = await api.sendChat(project.id, "Create a blog");
    expect(res.status).toBe("completed");
    expect(res.message).toBe("Finished 3 task(s).");
    expect(res.tasks.every((t) => t.status === "succeeded")).toBe(true);

    const { files } = await api.listFiles(project.id);
    expect(files.map((f) => f.path)).toEqual(["about.html", "index.html", "style.css"]);
    const index = await api.getFileContent(project.id, "index.html");
    expect(index.content).toContain("<title>Home · My Blog</title>");
    expect(index.size).toBe(files.find((f) => f.path === "index.html")!.size);

    const logs = await api.getLogs(project.id);
    expect(logs.entries.map((e) => [e.command, e.status])).toEqual([
      ["write_file index.html", "succeeded"],
      ["write_file about.html", "succeeded"],
      ["write_file style.css", "succeeded"],
    ]);
    expect(logs.next_after_id).toBe(3);
    expect((await api.getLogs(project.id, 2)).entries.map((e) => e.id)).toEqual([3]);

    const preview = await api.getPreview(project.id);
    expect(preview.status).toBe("static");
    expect(preview.url).toMatch(/^data:text\/html/);
  });

  it("holds a command for approval and fails it once approved, as Sprint 3 does", async () => {
    const api = new MockAgentApi(0);
    const { id } = await api.createProject("P");
    const res = await api.sendChat(id, "run npm install");
    expect(res.status).toBe("waiting_for_approval");
    expect(res.message).toBe("I need your approval to run: npm install");
    const pending = res.pending_action!;
    expect(pending.command_hash).toMatch(/^[0-9a-f]{64}$/);

    await expect(api.sendChat(id, "Create a blog")).rejects.toMatchObject({ code: "pending_action_exists" });
    await expect(api.approveAction(pending.id, "0".repeat(64))).rejects.toMatchObject({
      code: "approval_mismatch",
    });

    const decided = await api.approveAction(pending.id, pending.command_hash);
    expect(decided).toMatchObject({ status: "failed", decision: "approved", pending_action: null });
    expect(decided.tasks[0].status).toBe("failed");
    const [entry] = (await api.getLogs(id)).entries;
    expect(entry).toMatchObject({ command: "npm install", status: "failed" });
    expect(entry.stderr).toMatch(/closed this sprint/);

    await expect(api.rejectAction(pending.id, pending.command_hash)).rejects.toMatchObject({
      code: "action_already_decided",
    });
  });

  it("cancels the task when a command is rejected, and treats a repeat as a no-op", async () => {
    const api = new MockAgentApi(0);
    const { id } = await api.createProject("P");
    const pending = (await api.sendChat(id, "run make deploy")).pending_action!;

    const decided = await api.rejectAction(pending.id, pending.command_hash);
    expect(decided).toMatchObject({ status: "cancelled", decision: "rejected" });
    expect(decided.message).toBe("Cancelled: 0 task(s) done before it stopped.");

    const again = await api.rejectAction(pending.id, pending.command_hash);
    expect(again.message).toMatch(/^This request was already rejected\./);
  });

  it("keeps projects separate", async () => {
    const api = new MockAgentApi(0);
    const a = await api.createProject("A");
    const b = await api.createProject("B");
    await api.sendChat(a.id, "Create a blog");
    expect((await api.getTasks(b.id)).tasks).toHaveLength(0);
    expect((await api.listFiles(b.id)).files).toHaveLength(0);
    expect((await api.getLogs(b.id)).entries).toHaveLength(0);
  });

  it("rejects unknown projects and files like the API does", async () => {
    const api = new MockAgentApi(0);
    await expect(api.sendChat(42, "hi")).rejects.toMatchObject({ status: 404, code: "project_not_found" });
    const { id } = await api.createProject("P");
    await expect(api.getFileContent(id, "nope.html")).rejects.toMatchObject({
      status: 404,
      code: "file_not_found",
    });
  });
});

describe("createApi", () => {
  it("defaults to the mock", () => {
    expect(createApi({}).mode).toBe("mock");
  });

  it("uses the live API when VITE_USE_MOCK=false", () => {
    expect(createApi({ VITE_USE_MOCK: "false" }).mode).toBe("live");
  });
});
