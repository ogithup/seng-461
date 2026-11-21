import { HttpAgentApi } from "./httpApi";
import { MockAgentApi } from "./mockApi";
import type { AgentApi } from "./types";

export const DEFAULT_API_BASE_URL = "http://localhost:8000/api";

const OFF = new Set(["false", "0", "no", "off"]);
const ON = new Set(["true", "1", "yes", "on"]);

/**
 * `VITE_USE_MOCK`: unset or empty means mock (the safe default for development and tests);
 * false/0/no/off (any case) means the live API. Anything else stays on the mock, with a warning.
 */
export function isMockMode(raw: string | undefined): boolean {
  const value = (raw ?? "").trim().toLowerCase();
  if (value === "" || ON.has(value)) return true;
  if (OFF.has(value)) return false;
  console.warn(`VITE_USE_MOCK=${JSON.stringify(raw)} is not true/false; using the mock API.`);
  return true;
}

/** Picks the API client from Vite env vars (see frontend/.env.example and frontend/.env.live). */
export function createApi(env: Record<string, string | undefined> = import.meta.env): AgentApi {
  if (isMockMode(env.VITE_USE_MOCK)) return new MockAgentApi();
  return new HttpAgentApi({ baseUrl: env.VITE_API_BASE_URL?.trim() || DEFAULT_API_BASE_URL });
}

export * from "./types";
export { ApiError, describeError } from "./errors";
