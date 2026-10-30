import { ApiError } from "./errors";
import type {
  ActionDecisionResponse,
  AgentApi,
  ChatResponse,
  FileContent,
  FileList,
  LogsPage,
  PreviewInfo,
  Project,
  ProjectCreated,
  ProjectState,
} from "./types";

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
    return this.request<ProjectState>("GET", `/tasks?${query({ project_id: projectId })}`);
  }

  approveAction(actionId: number, commandHash: string) {
    return this.decide(actionId, "approve", commandHash);
  }

  rejectAction(actionId: number, commandHash: string) {
    return this.decide(actionId, "reject", commandHash);
  }

  getLogs(projectId: number, afterId = 0, limit = 100) {
    return this.request<LogsPage>(
      "GET",
      `/logs?${query({ project_id: projectId, after_id: afterId, limit })}`,
    );
  }

  listFiles(projectId: number) {
    return this.request<FileList>("GET", `/files?${query({ project_id: projectId })}`);
  }

  getFileContent(projectId: number, path: string) {
    return this.request<FileContent>("GET", `/files/content?${query({ project_id: projectId, path })}`);
  }

  async getPreview(projectId: number) {
    const info = await this.request<PreviewInfo>("GET", `/preview?${query({ project_id: projectId })}`);
    // The API answers with a path ("/api/preview/1/"); the iframe needs it on the API's origin.
    return info.url ? { ...info, url: this.absolute(info.url) } : info;
  }

  private decide(actionId: number, decision: "approve" | "reject", commandHash: string) {
    return this.request<ActionDecisionResponse>(
      "POST",
      `/actions/${encodeURIComponent(actionId)}/${decision}`,
      { command_hash: commandHash },
    );
  }

  private absolute(url: string): string {
    const page = typeof window !== "undefined" ? window.location.href : "http://localhost/";
    return new URL(url, new URL(this.baseUrl, page)).toString();
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

function query(params: Record<string, string | number>): string {
  return new URLSearchParams(
    Object.entries(params).map(([k, v]) => [k, String(v)]),
  ).toString();
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
