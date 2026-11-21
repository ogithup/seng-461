import { afterEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_API_BASE_URL, createApi, isMockMode } from "../services";
import { MockAgentApi, classify, fakePlan, unsupportedReason } from "../services/mockApi";

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

describe("MockAgentApi — Sprint 4 states", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("creates every task as pending, then runs them one by one while POST /chat is open", async () => {
    vi.useFakeTimers();
    const api = new MockAgentApi(100);
    const created = api.createProject("P");
    await vi.advanceTimersByTimeAsync(100);
    const { id } = await created;

    const reply = api.sendChat(id, "Create a blog");
    await vi.advanceTimersByTimeAsync(100); // planned: task 1 running, the rest pending
    const during = api.getTasks(id);
    await vi.advanceTimersByTimeAsync(100); // task 1 done, task 2 running
    const mid = await during;
    expect(mid.status).toBe("running");
    expect(mid.tasks.map((t) => t.status)).toEqual(["succeeded", "running", "pending"]);

    await vi.advanceTimersByTimeAsync(300);
    const res = await reply;
    expect(res.status).toBe("completed");
    expect(res.tasks.map((t) => t.status)).toEqual(["succeeded", "succeeded", "succeeded"]);
  });

  it("simulates a failed write: the task fails with a reason in the log, later ones are skipped", async () => {
    const api = new MockAgentApi(0);
    const { id } = await api.createProject("P");

    const res = await api.sendChat(id, "Create a blog called Notes (simulate failure)");

    expect(res.status).toBe("failed");
    expect(res.message).toBe("Stopped after a failure: 1 task(s) done, 1 not run.");
    expect(res.tasks.map((t) => [t.prompt, t.status])).toEqual([
      ['Write index.html (blog site "Notes")', "succeeded"],
      ['Write about.html (blog site "Notes")', "failed"],
      ['Write style.css (blog site "Notes")', "skipped"],
    ]);
    const failed = (await api.getLogs(id)).entries.find((e) => e.status === "failed")!;
    expect(failed).toMatchObject({ task_id: res.tasks[1].id, command: "write_file about.html" });
    expect(failed.stderr).toMatch(/Mock failure: about\.html was not written/);
    expect((await api.listFiles(id)).files.map((f) => f.path)).toEqual(["index.html"]);
  });

  it("declines unsupported sites with 422 unsupported_request and creates no task", async () => {
    const api = new MockAgentApi(0);
    const { id } = await api.createProject("P");

    await expect(api.sendChat(id, "Build an online shop")).rejects.toMatchObject({
      status: 422,
      code: "unsupported_request",
      message: "Online shops are not supported yet. Try a blog, portfolio or landing page.",
    });
    expect((await api.getTasks(id)).tasks).toHaveLength(0);
    expect(unsupportedReason("I need a booking system")).toBe("Only blogs, portfolios and landing pages are supported yet.");
    expect(unsupportedReason("Create a blog about my restoration hobby")).toBeNull();
  });

  it("allows one request per project at a time, like the API's project lock", async () => {
    const api = new MockAgentApi(5);
    const { id } = await api.createProject("P");

    const first = api.sendChat(id, "Create a blog");
    await new Promise((r) => setTimeout(r, 7)); // first one is now running its tasks
    await expect(api.sendChat(id, "Create a portfolio")).rejects.toMatchObject({
      status: 409,
      code: "project_busy",
      retryable: true,
    });
    expect((await first).status).toBe("completed");
  });
});

describe("mock / live configuration", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("defaults to the mock", () => {
    expect(createApi({}).mode).toBe("mock");
    expect(createApi({ VITE_USE_MOCK: "" }).mode).toBe("mock");
    expect(createApi({}).target).toMatch(/mock/);
  });

  it("uses the live API when VITE_USE_MOCK=false", () => {
    expect(createApi({ VITE_USE_MOCK: "false" }).mode).toBe("live");
  });

  it.each(["false", "FALSE", " False ", "0", "no", "off"])("treats VITE_USE_MOCK=%j as live", (value) => {
    expect(isMockMode(value)).toBe(false);
  });

  it.each([undefined, "", "true", "TRUE", "1", "yes", "on"])("treats VITE_USE_MOCK=%j as mock", (value) => {
    expect(isMockMode(value)).toBe(true);
  });

  it("stays on the mock, with a warning, for a value it doesn't recognise", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(isMockMode("fasle")).toBe(true);
    expect(warn).toHaveBeenCalledWith(expect.stringContaining("fasle"));
  });

  it("points the live client at VITE_API_BASE_URL, or the default local API", () => {
    expect(createApi({ VITE_USE_MOCK: "false" }).target).toBe(DEFAULT_API_BASE_URL);
    expect(DEFAULT_API_BASE_URL).toBe("http://localhost:8000/api");
    expect(
      createApi({ VITE_USE_MOCK: "false", VITE_API_BASE_URL: " https://api.example.com/api/ " }).target,
    ).toBe("https://api.example.com/api");
  });
});
