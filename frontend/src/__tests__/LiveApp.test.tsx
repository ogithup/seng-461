import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import App from "../App";
import { ApiError } from "../services/errors";
import { HttpAgentApi } from "../services/httpApi";
import { MockAgentApi } from "../services/mockApi";

// The UI on the live client (HttpAgentApi), over a fake HTTP backend that speaks the contract in
// docs/api-contracts.md. This covers the live code path — URLs, headers, JSON, error envelopes,
// preview URL resolution — without a running server. The integrated run against the real
// backend is live.smoke.test.ts.

const BASE = "http://api.test/api";

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

interface Call {
  method: string;
  path: string;
  body?: unknown;
  headers: Record<string, string>;
}

/** Routes requests to a MockAgentApi for state; answers preview like the real API does. */
function fakeBackend() {
  const state = new MockAgentApi(0);
  const calls: Call[] = [];
  const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    const method = init?.method ?? "GET";
    const body = typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
    calls.push({ method, path: url.pathname + url.search, body, headers: (init?.headers ?? {}) as Record<string, string> });
    const q = url.searchParams;
    const pid = Number(q.get("project_id"));
    try {
      switch (`${method} ${url.pathname}`) {
        case "GET /api/health":
          return json(200, await state.health());
        case "GET /api/projects":
          return json(200, await state.listProjects());
        case "POST /api/projects":
          return json(201, await state.createProject(body.name));
        case "POST /api/chat":
          return json(200, await state.sendChat(body.project_id, body.message));
        case "GET /api/tasks":
          return json(200, await state.getTasks(pid));
        case "GET /api/logs":
          return json(200, await state.getLogs(pid, Number(q.get("after_id")), Number(q.get("limit"))));
        case "GET /api/files":
          return json(200, await state.listFiles(pid));
        case "GET /api/files/content":
          return json(200, await state.getFileContent(pid, q.get("path")!));
        case "GET /api/preview": {
          const { files } = await state.listFiles(pid);
          return json(
            200,
            files.some((f) => f.path === "index.html")
              ? { project_id: pid, status: "static", url: `/api/preview/${pid}/` }
              : { project_id: pid, status: "unavailable", url: null },
          );
        }
      }
      return json(404, { error: { code: "not_found", message: "Not Found" } });
    } catch (err) {
      if (!(err instanceof ApiError)) throw err;
      return json(err.status, { error: { code: err.code, message: err.message, retryable: err.retryable } });
    }
  });
  return { fetchImpl, calls };
}

const region = (name: string) => screen.getByRole("region", { name });

async function createProject(name: string) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Project name"), name);
  await user.click(screen.getByRole("button", { name: "Create project" }));
  await waitFor(() => expect(screen.getByLabelText("Message to the agent")).toBeEnabled());
  return user;
}

describe("App on the live API client", () => {
  it("creates a project, generates a site, and shows its files and preview", async () => {
    const { fetchImpl, calls } = fakeBackend();
    render(<App api={new HttpAgentApi({ baseUrl: BASE, fetchImpl })} />);

    expect(await screen.findByText("Live API · connected")).toBeInTheDocument();
    expect(screen.getByTestId("api-mode")).toHaveAttribute("title", BASE);
    const user = await createProject("Sprint 4 Demo");

    const created = calls.find((c) => c.method === "POST" && c.path === "/api/projects")!;
    expect(created.body).toEqual({ name: "Sprint 4 Demo" });
    expect(created.headers["Idempotency-Key"]).toMatch(/\S{8,}/);

    await user.type(screen.getByLabelText("Message to the agent"), "Create a blog");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("All 3 task(s) succeeded.")).toBeInTheDocument();
    const chat = calls.find((c) => c.method === "POST" && c.path === "/api/chat")!;
    expect(chat.body).toEqual({ project_id: 1, message: "Create a blog" });
    expect(calls.some((c) => c.path === "/api/tasks?project_id=1")).toBe(true);

    const files = region("Generated files");
    await user.click(await within(files).findByRole("button", { name: /index\.html/ }));
    expect(await within(files).findByLabelText("Contents of index.html")).toHaveTextContent("<title>Home · My Blog</title>");
    expect(calls.some((c) => c.path === "/api/files/content?project_id=1&path=index.html")).toBe(true);

    const frame = await within(region("Preview")).findByTitle("Website preview");
    expect(frame).toHaveAttribute("src", "http://api.test/api/preview/1/");
    expect(frame).toHaveAttribute("sandbox", "allow-scripts"); // no allow-same-origin
    expect(within(region("Preview")).getByRole("link", { name: "Open in new tab" })).toHaveAttribute(
      "href",
      "http://api.test/api/preview/1/",
    );
    // Real backend data is not labelled as mock data.
    expect(screen.queryByText(/made in the browser/)).not.toBeInTheDocument();
  });

  it("shows the backend's unsupported_request message as a failure", async () => {
    const { fetchImpl, calls } = fakeBackend();
    render(<App api={new HttpAgentApi({ baseUrl: BASE, fetchImpl })} />);
    const user = await createProject("Shop");

    await user.type(screen.getByLabelText("Message to the agent"), "Build an online shop{Enter}");

    expect(await within(region("Agent status")).findByText(/Online shops are not supported yet/)).toBeInTheDocument();
    expect(screen.getByTestId("request-status")).toHaveTextContent("Failed");
    expect(screen.getByText("No tasks yet.")).toBeInTheDocument();
    expect(calls.filter((c) => c.path === "/api/chat")).toHaveLength(1); // a 422 is not retried
  });

  it("says when the backend can't be reached", async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    render(<App api={new HttpAgentApi({ baseUrl: BASE, fetchImpl })} />);

    expect(await screen.findByText("Live API · unreachable")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/Can't reach the backend/);
    expect(screen.getByTestId("api-mode").getAttribute("title")).toContain(BASE);

    // Recovers once the backend is up.
    const { fetchImpl: up } = fakeBackend();
    fetchImpl.mockImplementation(up);
    await userEvent.setup().click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Live API · connected")).toBeInTheDocument();
  });

  it("reports a response it can't read instead of rendering it", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) =>
      String(input).endsWith("/projects")
        ? new Response("<html>proxy error page</html>", { status: 200, headers: { "Content-Type": "text/html" } })
        : json(200, { status: "ok" }),
    );
    render(<App api={new HttpAgentApi({ baseUrl: BASE, fetchImpl })} />);

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/response this app doesn't understand/));
  });
});
