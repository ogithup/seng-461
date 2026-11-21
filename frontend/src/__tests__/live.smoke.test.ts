// @vitest-environment node
//
// Integrated smoke test: the frontend's live client against a running backend. Skipped unless
// VITE_SMOKE_API_URL is set, so `npm test` never needs a server. Run it with the API up:
//
//   uvicorn backend.main:app --port 8000                      # from the repo root
//   VITE_SMOKE_API_URL=http://127.0.0.1:8000/api npm run test:smoke
//
// It creates projects in whatever database that backend uses. Set
// VITE_SMOKE_EXPECT_UNSUPPORTED=true once the Sprint 4 interpreter is merged, to make the
// unsupported-request check mandatory instead of skipping it on a backend that lacks it.
// VITE_SMOKE_ORIGIN changes the browser origin checked against CORS (default :5173).
import { describe, expect, it } from "vitest";
import { ApiError } from "../services/errors";
import { HttpAgentApi } from "../services/httpApi";

const BASE = import.meta.env.VITE_SMOKE_API_URL;
const EXPECT_UNSUPPORTED = import.meta.env.VITE_SMOKE_EXPECT_UNSUPPORTED === "true";
// The Vite dev server origin, allowed by the backend's CORS_ORIGINS by default.
const ORIGIN = import.meta.env.VITE_SMOKE_ORIGIN || "http://localhost:5173";
const stamp = new Date().toISOString().slice(11, 19);

describe.skipIf(!BASE)(`live backend smoke test (${BASE ?? "VITE_SMOKE_API_URL not set"})`, () => {
  const api = new HttpAgentApi({ baseUrl: BASE ?? "", maxRetries: 2, retryDelayMs: 500 });
  const raw = (path: string, init?: RequestInit) => fetch(new URL(path, BASE).toString(), init);

  it("is up and lets the frontend's origin call it (CORS)", async () => {
    expect(await api.health()).toEqual({ status: "ok" });
    const preflight = await raw(`${BASE}/chat`, {
      method: "OPTIONS",
      headers: {
        Origin: ORIGIN,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,idempotency-key",
      },
    });
    expect(preflight.headers.get("access-control-allow-origin")).toBe(ORIGIN);
    expect(preflight.headers.get("access-control-allow-headers")?.toLowerCase()).toContain("idempotency-key");
  });

  it("creates a project, generates a blog, and serves its files and a sandboxed preview", async () => {
    const project = await api.createProject(`Sprint 4 Demo ${stamp}`);
    expect(project.name).toBe(`Sprint 4 Demo ${stamp}`);
    expect((await api.listProjects()).some((p) => p.id === project.id)).toBe(true);
    expect(await api.getTasks(project.id)).toMatchObject({ status: "idle", tasks: [] });
    expect(await api.getPreview(project.id)).toMatchObject({ status: "unavailable" });

    const res = await api.sendChat(project.id, "Create a blog called Smoke Notes");
    expect(res.status).toBe("completed");
    expect(res.tasks.length).toBeGreaterThan(0);
    expect(res.tasks.every((t) => t.status === "succeeded")).toBe(true);
    expect(res.message).toBe(`Finished ${res.tasks.length} task(s).`);
    expect(await api.getTasks(project.id)).toMatchObject({ status: "completed", tasks: res.tasks });

    // Task results match the log: one successful write per task.
    const logs = await api.getLogs(project.id, 0, 500);
    expect(logs.entries).toHaveLength(res.tasks.length);
    expect(logs.entries.every((e) => e.status === "succeeded" && e.command.startsWith("write_file "))).toBe(true);
    expect(new Set(logs.entries.map((e) => e.task_id))).toEqual(new Set(res.tasks.map((t) => t.id)));

    const { files } = await api.listFiles(project.id);
    const paths = files.map((f) => f.path);
    expect(paths).toContain("index.html");
    expect(paths.sort()).toEqual(logs.entries.map((e) => e.command.slice("write_file ".length)).sort());
    const index = await api.getFileContent(project.id, "index.html");
    expect(index.content).toContain("Smoke Notes");
    expect(index.size).toBe(files.find((f) => f.path === "index.html")!.size);

    const preview = await api.getPreview(project.id);
    expect(preview.status).toBe("static");
    expect(preview.url).toBe(new URL(`/api/preview/${project.id}/`, BASE).toString());
    const page = await raw(preview.url!);
    expect(page.status).toBe(200);
    expect(page.headers.get("content-type")).toMatch(/^text\/html/);
    expect(page.headers.get("content-security-policy")).toBe("sandbox allow-scripts");
    expect(await page.text()).toContain("Smoke Notes");
    // Every generated file is reachable relative to the preview URL, as the site's links expect.
    for (const path of paths) {
      expect((await raw(new URL(path, preview.url!).toString())).status, path).toBe(200);
    }
  });

  it("adds a second request's tasks after the first, with different output", async () => {
    const { id } = await api.createProject(`Two sites ${stamp}`);
    const blog = await api.sendChat(id, "Create a blog");
    const blogIndex = (await api.getFileContent(id, "index.html")).content;

    const portfolio = await api.sendChat(id, "Create a portfolio for Ada Lovelace");

    expect(portfolio.tasks.slice(0, blog.tasks.length)).toEqual(blog.tasks);
    const added = portfolio.tasks.slice(blog.tasks.length);
    expect(added.length).toBeGreaterThan(0);
    expect(Math.min(...added.map((t) => t.id))).toBeGreaterThan(Math.max(...blog.tasks.map((t) => t.id)));
    expect((await api.getFileContent(id, "index.html")).content).not.toBe(blogIndex);
  });

  it("refuses an unsupported request without creating tasks (needs the Sprint 4 interpreter)", async (ctx) => {
    const { id } = await api.createProject(`Unsupported ${stamp}`);
    const result = await api.sendChat(id, "Build an online shop").then(
      (ok) => ok,
      (err: unknown) => err,
    );
    if (!(result instanceof ApiError) && !EXPECT_UNSUPPORTED) {
      console.warn("This backend built a site for 'Build an online shop': it has no unsupported_request yet.");
      ctx.skip();
    }
    expect(result).toBeInstanceOf(ApiError);
    expect(result).toMatchObject({ status: 422, code: "unsupported_request" });
    expect((result as ApiError).message).toMatch(/not supported/);
    expect((await api.getTasks(id)).tasks).toHaveLength(0);
  });

  it("answers bad requests with the error envelope the UI relies on", async () => {
    const { id } = await api.createProject(`Errors ${stamp}`);
    const error = (p: Promise<unknown>) => p.then(() => null, (e: unknown) => e as ApiError);

    expect(await error(api.getTasks(999_999_999))).toMatchObject({ status: 404, code: "project_not_found" });
    expect(await error(api.getFileContent(id, "missing.html"))).toMatchObject({ status: 404, code: "file_not_found" });
    expect(await error(api.getFileContent(id, "../secret.txt"))).toMatchObject({ status: 403, code: "path_not_allowed" });
    const invalid = await error(api.sendChat(id, ""));
    expect(invalid).toMatchObject({ status: 422, code: "validation_error" });
    expect(invalid!.requestId).toMatch(/\w+/);
  });
});
