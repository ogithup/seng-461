import { ApiError } from "./errors";
import type { AgentApi, ChatResponse, Project, ProjectCreated, ProjectState } from "./types";

type Fetch = typeof fetch;

export interface HttpApiOptions {
  baseUrl: string;
  fetchImpl?: Fetch;
  /** How many times to retry `retryable` errors (409 project_busy, 429, 502 agent_error). */
  maxRetries?: number;
  /** Delay before a retry when the server gives no Retry-After header. */
  retryDelayMs?: number;
  sleep?: (ms: number) => Promise<void>;
}

const defaultSleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

/** Talks to Oğuz's REST API (backend/api). Only this file knows about URLs and headers. */
export class HttpAgentApi implements AgentApi {
  readonly mode = "live" as const;
  private readonly baseUrl: string;
  private readonly fetchImpl: Fetch;
  private readonly maxRetries: number;
  private readonly retryDelayMs: number;
  private readonly sleep: (ms: number) => Promise<void>;

  constructor(opts: HttpApiOptions) {
    this.baseUrl = opts.baseUrl.replace(/\/+$/, "");
    this.fetchImpl = opts.fetchImpl ?? ((...args) => fetch(...args));
    this.maxRetries = opts.maxRetries ?? 2;
    this.retryDelayMs = opts.retryDelayMs ?? 1000;
    this.sleep = opts.sleep ?? defaultSleep;
  }

  health() {
    return this.request<{ status: string }>("GET", "/health");
  }

  createProject(name: string) {
    return this.request<ProjectCreated>("POST", "/projects", { name });
  }

  listProjects() {
    return this.request<Project[]>("GET", "/projects");
  }

  sendChat(projectId: number, message: string) {
    return this.request<ChatResponse>("POST", "/chat", { project_id: projectId, message });
  }

  getTasks(projectId: number) {
    return this.request<ProjectState>("GET", `/tasks?project_id=${encodeURIComponent(projectId)}`);
  }

  private async request<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (method === "POST") {
      headers["Content-Type"] = "application/json";
      // One key per user submission, reused on retry, so a retried POST is never applied twice.
      headers["Idempotency-Key"] = newIdempotencyKey();
    }

    for (let attempt = 0; ; attempt++) {
      let res: Response;
      try {
        res = await this.fetchImpl(this.baseUrl + path, {
          method,
          headers,
          body: body === undefined ? undefined : JSON.stringify(body),
        });
      } catch {
        throw new ApiError(0, { code: "network_error", message: "Network error", retryable: true });
      }

      if (res.ok) return (await res.json()) as T;

      const error = new ApiError(res.status, await readErrorBody(res));
      if (!error.retryable || attempt >= this.maxRetries) throw error;
      await this.sleep(retryAfterMs(res) ?? this.retryDelayMs);
    }
  }
}

async function readErrorBody(res: Response) {
  try {
    const data = await res.json();
    if (data && typeof data.error?.code === "string") return data.error;
  } catch {
    /* not JSON */
  }
  return { code: `http_${res.status}`, message: `Request failed (${res.status}).` };
}

function retryAfterMs(res: Response): number | undefined {
  const raw = res.headers.get("Retry-After");
  const seconds = raw ? Number(raw) : NaN;
  return Number.isFinite(seconds) && seconds >= 0 ? Math.min(seconds, 30) * 1000 : undefined;
}
