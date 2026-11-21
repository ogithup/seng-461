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
// `unsupported_request` is deliberately absent: its message is written for the user by the agent
// (docs/sprint4-contracts.md §5) and is shown as the server sent it.
const FRIENDLY: Record<string, string> = {
  network_error: "Can't reach the backend. Is the API running, and is VITE_API_BASE_URL right?",
  timeout: "The backend took too long to answer.",
  invalid_response:
    "The backend sent a response this app doesn't understand. Check that the frontend and backend versions match.",
  not_found: "The backend has no such endpoint. Check VITE_API_BASE_URL (it should end in /api).",
  method_not_allowed: "The backend doesn't accept this request. Check VITE_API_BASE_URL.",
  project_not_found: "That project no longer exists.",
  project_busy: "The agent is still working on this project. Try again in a moment.",
  pending_action_exists: "A command is waiting for approval before a new request can start.",
  rate_limited: "Too many requests. Please wait a moment.",
  agent_error: "The agent couldn't plan this request. Please try again.",
  agent_empty_plan: "The agent returned an empty plan. Try rephrasing your request.",
  validation_error: "The request wasn't valid.",
  request_too_large: "That message is too large.",
  idempotency_conflict: "This request clashed with an earlier one. Please send it again.",
  idempotency_in_progress: "The same request is still being processed. Try again in a moment.",
  idempotency_key_required: "The backend requires an Idempotency-Key header on this request.",
  internal_error: "Something went wrong on the server.",
  action_not_found: "That approval request no longer exists.",
  action_expired: "This approval request has expired. Send the request again if you still need it.",
  action_already_decided: "Someone already decided on this command.",
  approval_mismatch: "The pending command changed since you looked at it. Review it again.",
  file_not_found: "That file is no longer in the project.",
  path_not_allowed: "That file is outside the project workspace.",
  file_too_large: "That file is too large to show here.",
  unsupported_file_type: "Only text files can be shown here.",
};

// v1 of the API has no authentication (docs/api-contracts.md, "Security notes"). If a deployment
// puts one in front of it, say so plainly instead of showing a raw status code.
const BY_STATUS: Record<number, string> = {
  401: "The backend requires you to sign in, which this app doesn't support yet.",
  403: "The backend refused access to this resource.",
};

export function describeError(err: unknown): string {
  if (err instanceof ApiError) {
    const base = FRIENDLY[err.code] ?? BY_STATUS[err.status] ?? (err.message || `Request failed (${err.status}).`);
    const detail = err.code === "validation_error" && err.details?.[0]?.message;
    return detail ? `${base} (${detail})` : base;
  }
  if (err instanceof Error) return err.message;
  return "Unexpected error.";
}

/**
 * True when the backend answered that it did not carry out the request: a 4xx (bad input, an
 * unsupported request, a conflict) or a 502 from planning. Nothing was created in that case.
 * A network failure, timeout or 500 is different: the request may or may not have been applied.
 */
export function wasRefused(err: unknown): boolean {
  if (!(err instanceof ApiError)) return false;
  if (err.code === "idempotency_in_progress") return false; // the same request is running
  return (err.status >= 400 && err.status < 500) || err.status === 502;
}
