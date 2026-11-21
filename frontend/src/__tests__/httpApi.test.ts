import { describe, expect, it, vi } from "vitest";
import { ApiError, describeError, wasRefused } from "../services/errors";
import { HttpAgentApi } from "../services/httpApi";

function json(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

describe("HttpAgentApi", () => {
  it("posts chat messages in the contract shape with an Idempotency-Key", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      json(200, { project_id: 1, status: "completed", tasks: [], pending_action: null, message: "ok" }),
    );
    const api = new HttpAgentApi({ baseUrl: "http://api.test/api/", fetchImpl });

    const res = await api.sendChat(1, "Create a blog");

    expect(res.message).toBe("ok");
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe("http://api.test/api/chat");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ project_id: 1, message: "Create a blog" });
    expect(init.headers["Idempotency-Key"]).toMatch(/\S{8,}/);
  });

  it("GETs tasks for a project without an Idempotency-Key", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      json(200, { project_id: 3, status: "idle", tasks: [], pending_action: null }),
    );
    const api = new HttpAgentApi({ baseUrl: "http://api.test/api", fetchImpl });

    await api.getTasks(3);

    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe("http://api.test/api/tasks?project_id=3");
    expect(init.headers["Idempotency-Key"]).toBeUndefined();
  });

  it("turns the error envelope into an ApiError", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      json(404, { error: { code: "project_not_found", message: "Project not found.", retryable: false } }),
    );
    const api = new HttpAgentApi({ baseUrl: "http://api.test/api", fetchImpl });

    const err = await api.getTasks(99).catch((e) => e);

    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(404);
    expect(err.code).toBe("project_not_found");
    expect(describeError(err)).toBe("That project no longer exists.");
  });

  it("retries a retryable 409 project_busy with the same Idempotency-Key", async () => {
    const busy = { error: { code: "project_busy", message: "busy", retryable: true } };
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(json(409, busy, { "Retry-After": "0" }))
      .mockResolvedValueOnce(
        json(200, { project_id: 1, status: "completed", tasks: [], pending_action: null, message: "ok" }),
      );
    const sleep = vi.fn().mockResolvedValue(undefined);
    const api = new HttpAgentApi({ baseUrl: "http://api.test/api", fetchImpl, sleep });

    await api.sendChat(1, "hi");

    expect(fetchImpl).toHaveBeenCalledTimes(2);
    expect(sleep).toHaveBeenCalledWith(0);
    const key1 = fetchImpl.mock.calls[0][1].headers["Idempotency-Key"];
    const key2 = fetchImpl.mock.calls[1][1].headers["Idempotency-Key"];
    expect(key1).toBe(key2);
  });

  it("does not retry non-retryable errors", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      json(409, { error: { code: "pending_action_exists", message: "pending", retryable: false } }),
    );
    const api = new HttpAgentApi({ baseUrl: "http://api.test/api", fetchImpl, sleep: vi.fn() });

    await expect(api.sendChat(1, "hi")).rejects.toMatchObject({ code: "pending_action_exists" });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("approves and rejects with the command_hash the human saw", async () => {
    const decided = { project_id: 1, status: "failed", tasks: [], pending_action: null, message: "m" };
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(json(200, { ...decided, action_id: 7, decision: "approved" }))
      .mockResolvedValueOnce(json(200, { ...decided, action_id: 8, decision: "rejected" }));
    const api = new HttpAgentApi({ baseUrl: "http://api.test/api", fetchImpl });
    const hash = "a".repeat(64);

    await api.approveAction(7, hash);
    await api.rejectAction(8, hash);

    const [approveUrl, approveInit] = fetchImpl.mock.calls[0];
    expect(approveUrl).toBe("http://api.test/api/actions/7/approve");
    expect(approveInit.method).toBe("POST");
    expect(JSON.parse(approveInit.body)).toEqual({ command_hash: hash });
    expect(fetchImpl.mock.calls[1][0]).toBe("http://api.test/api/actions/8/reject");
  });

  it("reads logs, files and file contents with encoded query parameters", async () => {
    const bodies: Record<string, unknown> = {
      logs: { project_id: 2, entries: [], next_after_id: 5 },
      files: { project_id: 2, files: [], truncated: false },
      content: { project_id: 2, path: "pages/a b&c.html", size: 0, content: "" },
    };
    const fetchImpl = vi.fn().mockImplementation((url: string) =>
      Promise.resolve(json(200, bodies[url.includes("/content") ? "content" : url.includes("/logs") ? "logs" : "files"])),
    );
    const api = new HttpAgentApi({ baseUrl: "http://api.test/api", fetchImpl });

    await api.getLogs(2, 5, 500);
    await api.listFiles(2);
    await api.getFileContent(2, "pages/a b&c.html");

    expect(fetchImpl.mock.calls.map((c) => c[0])).toEqual([
      "http://api.test/api/logs?project_id=2&after_id=5&limit=500",
      "http://api.test/api/files?project_id=2",
      "http://api.test/api/files/content?project_id=2&path=pages%2Fa+b%26c.html",
    ]);
  });

  it("resolves the preview path against the API's origin", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(json(200, { project_id: 4, status: "static", url: "/api/preview/4/" }))
      .mockResolvedValueOnce(json(200, { project_id: 5, status: "unavailable", url: null }));
    const api = new HttpAgentApi({ baseUrl: "http://localhost:8000/api", fetchImpl });

    expect((await api.getPreview(4)).url).toBe("http://localhost:8000/api/preview/4/");
    expect(await api.getPreview(5)).toEqual({ project_id: 5, status: "unavailable", url: null });
    expect(fetchImpl.mock.calls[0][0]).toBe("http://localhost:8000/api/preview?project_id=4");
  });

  it("explains file and approval errors in plain words", () => {
    const err = (code: string) => new ApiError(409, { code, message: "raw" });
    expect(describeError(err("action_expired"))).toMatch(/expired/);
    expect(describeError(err("approval_mismatch"))).toMatch(/changed since you looked/);
    expect(describeError(err("unsupported_file_type"))).toMatch(/Only text files/);
  });

  it("reports an unreachable backend as network_error", async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    const api = new HttpAgentApi({ baseUrl: "http://api.test/api", fetchImpl, maxRetries: 0 });

    const err = await api.health().catch((e) => e);

    expect(err.code).toBe("network_error");
    expect(describeError(err)).toMatch(/Can't reach the backend/);
  });

  it("creates a project with POST /projects {name} and an Idempotency-Key", async () => {
    const created = { id: 7, name: "Sprint 4 Demo", created_at: "2026-11-21T00:00:00Z", session_id: 3 };
    const fetchImpl = vi.fn().mockResolvedValue(json(201, created));
    const api = new HttpAgentApi({ baseUrl: "http://api.test/api", fetchImpl });

    expect(await api.createProject("Sprint 4 Demo")).toEqual(created);

    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe("http://api.test/api/projects");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ name: "Sprint 4 Demo" });
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(init.headers["Idempotency-Key"]).toMatch(/\S{8,}/);
    expect(api.target).toBe("http://api.test/api");
  });

  it("uses a new Idempotency-Key for each submission", async () => {
    const ok = () => json(200, { project_id: 1, status: "completed", tasks: [], pending_action: null, message: "ok" });
    const fetchImpl = vi.fn().mockImplementation(() => Promise.resolve(ok()));
    const api = new HttpAgentApi({ baseUrl: "http://api.test/api", fetchImpl });

    await api.sendChat(1, "a");
    await api.sendChat(1, "a");

    const [k1, k2] = fetchImpl.mock.calls.map((c) => c[1].headers["Idempotency-Key"]);
    expect(k1).not.toBe(k2);
  });

  it("reports a 2xx body that isn't JSON, or isn't the contract's shape, as invalid_response", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(new Response("<html>gateway</html>", { status: 200 }))
      .mockResolvedValueOnce(json(200, { project_id: 1, status: "idle" })) // no tasks
      .mockResolvedValueOnce(json(200, { project_id: 1, files: [{ path: 3 }], truncated: false }));
    const api = new HttpAgentApi({ baseUrl: "http://api.test/api", fetchImpl });

    for (const call of [() => api.getTasks(1), () => api.getTasks(1), () => api.listFiles(1)]) {
      const err = await call().catch((e) => e);
      expect(err).toBeInstanceOf(ApiError);
      expect(err.code).toBe("invalid_response");
    }
    expect(describeError(new ApiError(200, { code: "invalid_response", message: "x" }))).toMatch(
      /doesn't understand/,
    );
  });

  it("passes an unknown status through for the UI to show as unknown", async () => {
    const odd = { project_id: 1, status: "queued", tasks: [{ id: 1, project_id: 1, type: "step", status: "queued", prompt: "p" }] };
    const api = new HttpAgentApi({ baseUrl: "http://api.test/api", fetchImpl: vi.fn().mockResolvedValue(json(200, odd)) });

    expect((await api.getTasks(1)).tasks[0].status).toBe("queued");
  });

  it("accepts only an http(s) preview URL", async () => {
    const preview = (url: string) => json(200, { project_id: 1, status: "static", url });
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(preview("javascript:alert(1)"))
      .mockResolvedValueOnce(preview("https://previews.example/p/1/"));
    const api = new HttpAgentApi({ baseUrl: "http://api.test/api", fetchImpl });

    await expect(api.getPreview(1)).rejects.toMatchObject({ code: "invalid_response" });
    expect((await api.getPreview(1)).url).toBe("https://previews.example/p/1/");
  });

  it("gives up on a request that doesn't answer in time", async () => {
    const fetchImpl = vi.fn(
      (_url: RequestInfo | URL, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init!.signal!.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
        }),
    );
    const api = new HttpAgentApi({ baseUrl: "http://api.test/api", fetchImpl, timeoutMs: 10 });

    const err = await api.sendChat(1, "Create a blog").catch((e) => e);

    expect(err).toMatchObject({ status: 0, code: "timeout" });
    expect(describeError(err)).toBe("The backend took too long to answer.");
    expect(fetchImpl).toHaveBeenCalledTimes(1); // not retried
  });

  it("explains authentication, unknown routes and non-JSON errors", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(json(401, { detail: "Not authenticated" }))
      .mockResolvedValueOnce(json(404, { error: { code: "not_found", message: "Not Found" } }))
      .mockResolvedValueOnce(new Response("Service Unavailable", { status: 503 }));
    const api = new HttpAgentApi({ baseUrl: "http://api.test", fetchImpl, maxRetries: 0 });

    expect(describeError(await api.health().catch((e) => e))).toMatch(/requires you to sign in/);
    expect(describeError(await api.health().catch((e) => e))).toMatch(/should end in \/api/);
    const unavailable = await api.health().catch((e) => e);
    expect(unavailable).toMatchObject({ status: 503, code: "http_503" });
    expect(describeError(unavailable)).toBe("Request failed (503).");
  });

  it("shows the agent's own message for an unsupported request", () => {
    const err = new ApiError(422, {
      code: "unsupported_request",
      message: "Online shops are not supported yet. Try a blog, portfolio or landing page.",
    });
    expect(describeError(err)).toBe("Online shops are not supported yet. Try a blog, portfolio or landing page.");
  });

  it("tells refusals (nothing was done) from interruptions (it may have been done)", () => {
    const e = (status: number, code: string) => new ApiError(status, { code, message: "" });
    expect(wasRefused(e(422, "unsupported_request"))).toBe(true);
    expect(wasRefused(e(409, "project_busy"))).toBe(true);
    expect(wasRefused(e(502, "agent_error"))).toBe(true);
    expect(wasRefused(e(409, "idempotency_in_progress"))).toBe(false);
    expect(wasRefused(e(0, "network_error"))).toBe(false);
    expect(wasRefused(e(0, "timeout"))).toBe(false);
    expect(wasRefused(e(500, "internal_error"))).toBe(false);
    expect(wasRefused(new Error("boom"))).toBe(false);
  });
});
