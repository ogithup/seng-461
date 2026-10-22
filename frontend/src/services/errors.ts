import type { ApiErrorBody } from "./types";

/** An error returned by the API in its standard envelope, or a network failure. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryable: boolean;
  readonly requestId?: string;
  readonly details?: ApiErrorBody["details"];

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.retryable = Boolean(body.retryable);
    this.requestId = body.request_id;
    this.details = body.details;
  }
}

// Messages written for the person using the UI, keyed by the API's error codes.
const FRIENDLY: Record<string, string> = {
  network_error: "Can't reach the backend. Is the API running on port 8000?",
  project_not_found: "That project no longer exists.",
  project_busy: "The agent is still working on this project. Try again in a moment.",
  pending_action_exists: "A command is waiting for approval before a new request can start.",
  rate_limited: "Too many requests. Please wait a moment.",
  agent_error: "The agent couldn't plan this request. Please try again.",
  agent_empty_plan: "The agent returned an empty plan. Try rephrasing your request.",
  validation_error: "The request wasn't valid.",
  request_too_large: "That message is too large.",
  internal_error: "Something went wrong on the server.",
};

export function describeError(err: unknown): string {
  if (err instanceof ApiError) {
    const base = FRIENDLY[err.code] ?? err.message;
    const detail = err.code === "validation_error" && err.details?.[0]?.message;
    return detail ? `${base} (${detail})` : base;
  }
  if (err instanceof Error) return err.message;
  return "Unexpected error.";
}
