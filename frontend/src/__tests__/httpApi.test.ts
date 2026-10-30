import { describe, expect, it, vi } from "vitest";
import { ApiError, describeError } from "../services/errors";
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
    const fetchImpl = vi.fn().mockImplementation(() => Promise.resolve(json(200, {})));
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
});
