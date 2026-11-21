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
import {
  isFileContent,
  isFileList,
  isHealth,
  isLogsPage,
  isPreviewInfo,
  isProjectCreated,
  isProjectList,
  isProjectState,
  isStateWithMessage,
} from "./validate";

type Fetch = typeof fetch;
type Check = (value: unknown) => boolean;

export interface HttpApiOptions {
  baseUrl: string;
  fetchImpl?: Fetch;
  /** How many times to retry `retryable` errors (409 project_busy, 429, 502 agent_error). */
  maxRetries?: number;
  /** Delay before a retry when the server gives no Retry-After header. */
  retryDelayMs?: number;
  /**
   * Give up on an attempt that hasn't answered after this long (0 = never). POST /chat is
   * synchronous, so this bounds how long the UI shows a request as in flight; the backend may
   * still finish it, which the UI then picks up from GET /tasks.
   */
  timeoutMs?: number;
  sleep?: (ms: number) => Promise<void>;
}

export const DEFAULT_TIMEOUT_MS = 60_000;

const defaultSleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

const NOT_JSON = Symbol("not-json");

/** Talks to Oğuz's REST API (backend/api). Only this file knows about URLs and headers. */
export class HttpAgentApi implements AgentApi {
  readonly mode = "live" as const;
  readonly target: string;
  private readonly baseUrl: string;
  private readonly fetchImpl: Fetch;
  private readonly maxRetries: number;
  private readonly retryDelayMs: number;
  private readonly timeoutMs: number;
  private readonly sleep: (ms: number) => Promise<void>;

  constructor(opts: HttpApiOptions) {
    this.baseUrl = opts.baseUrl.replace(/\/+$/, "");
    this.target = this.baseUrl;
    this.fetchImpl = opts.fetchImpl ?? ((...args) => fetch(...args));
    this.maxRetries = opts.maxRetries ?? 2;
    this.retryDelayMs = opts.retryDelayMs ?? 1000;
    this.timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    this.sleep = opts.sleep ?? defaultSleep;
  }

  health() {
    return this.request<{ status: string }>("GET", "/health", isHealth);
  }

  createProject(name: string) {
    return this.request<ProjectCreated>("POST", "/projects", isProjectCreated, { name });
  }

  listProjects() {
    return this.request<Project[]>("GET", "/projects", isProjectList);
  }

  sendChat(projectId: number, message: string) {
    return this.request<ChatResponse>("POST", "/chat", isStateWithMessage, {
      project_id: projectId,
      message,
    });
  }

  getTasks(projectId: number) {
    return this.request<ProjectState>("GET", `/tasks?${query({ project_id: projectId })}`, isProjectState);
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
      isLogsPage,
    );
  }

  listFiles(projectId: number) {
    return this.request<FileList>("GET", `/files?${query({ project_id: projectId })}`, isFileList);
  }

  getFileContent(projectId: number, path: string) {
    return this.request<FileContent>(
      "GET",
      `/files/content?${query({ project_id: projectId, path })}`,
      isFileContent,
    );
  }

  async getPreview(projectId: number) {
    const info = await this.request<PreviewInfo>(
      "GET",
      `/preview?${query({ project_id: projectId })}`,
      isPreviewInfo,
    );
    if (!info.url) return info;
    // The API answers with a path ("/api/preview/1/"); the iframe needs it on the API's origin.
    // Only http(s) is accepted, so a bad response can't put e.g. a javascript: URL in the frame.
    const url = this.absolute(info.url);
    if (!url) throw invalidResponse(200, "GET /preview");
    return { ...info, url };
  }

  private decide(actionId: number, decision: "approve" | "reject", commandHash: string) {
    return this.request<ActionDecisionResponse>(
      "POST",
      `/actions/${encodeURIComponent(actionId)}/${decision}`,
      isStateWithMessage,
      { command_hash: commandHash },
    );
  }

  private absolute(url: string): string | null {
    const page = typeof window !== "undefined" ? window.location.href : "http://localhost/";
    try {
      const resolved = new URL(url, new URL(this.baseUrl, page));
      return resolved.protocol === "http:" || resolved.protocol === "https:" ? resolved.toString() : null;
    } catch {
      return null;
    }
  }

  private async request<T>(
    method: "GET" | "POST",
    path: string,
    check: Check,
    body?: unknown,
  ): Promise<T> {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (method === "POST") {
      headers["Content-Type"] = "application/json";
      // One key per user submission, reused on retry, so a retried POST is never applied twice.
      headers["Idempotency-Key"] = newIdempotencyKey();
    }
    const init = { method, headers, body: body === undefined ? undefined : JSON.stringify(body) };

    for (let attempt = 0; ; attempt++) {
      const { res, data } = await this.attempt(path, init);

      if (res.ok) {
        if (data === NOT_JSON || !check(data)) {
          throw invalidResponse(res.status, `${method} ${path.split("?")[0]}`);
        }
        return data as T;
      }

      const error = new ApiError(res.status, errorBody(res, data));
      if (!error.retryable || attempt >= this.maxRetries) throw error;
      await this.sleep(retryAfterMs(res) ?? this.retryDelayMs);
    }
  }

  /** One fetch, with its body read, bounded by `timeoutMs`. */
  private async attempt(path: string, init: RequestInit) {
    const controller =
      this.timeoutMs > 0 && typeof AbortController !== "undefined" ? new AbortController() : null;
    const timer = controller ? setTimeout(() => controller.abort(), this.timeoutMs) : undefined;
    const failed = () =>
      controller?.signal.aborted
        ? new ApiError(0, { code: "timeout", message: "The backend took too long to answer." })
        : new ApiError(0, { code: "network_error", message: "Network error", retryable: true });
    try {
      let res: Response;
      try {
        res = await this.fetchImpl(this.baseUrl + path, { ...init, signal: controller?.signal });
      } catch {
        throw failed();
      }
      let data: unknown = NOT_JSON;
      try {
        data = await res.json();
      } catch {
        if (controller?.signal.aborted) throw failed();
        /* not JSON: handled by the caller */
      }
      return { res, data };
    } finally {
      if (timer !== undefined) clearTimeout(timer);
    }
  }
}

function query(params: Record<string, string | number>): string {
  return new URLSearchParams(
    Object.entries(params).map(([k, v]) => [k, String(v)]),
  ).toString();
}

function errorBody(res: Response, data: unknown) {
  const error = (data as { error?: { code?: unknown; message?: unknown } } | null)?.error;
  if (data !== NOT_JSON && error && typeof error.code === "string") {
    return { ...error, code: error.code, message: typeof error.message === "string" ? error.message : "" };
  }
  return { code: `http_${res.status}`, message: `Request failed (${res.status}).` };
}

function invalidResponse(status: number, what: string) {
  return new ApiError(status, {
    code: "invalid_response",
    message: `Unexpected response from ${what}.`,
  });
}

function retryAfterMs(res: Response): number | undefined {
  const raw = res.headers.get("Retry-After");
  const seconds = raw ? Number(raw) : NaN;
  return Number.isFinite(seconds) && seconds >= 0 ? Math.min(seconds, 30) * 1000 : undefined;
}
