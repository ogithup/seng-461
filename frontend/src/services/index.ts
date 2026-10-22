import { HttpAgentApi } from "./httpApi";
import { MockAgentApi } from "./mockApi";
import type { AgentApi } from "./types";

/** Picks the API client from Vite env vars (see frontend/.env.example). */
export function createApi(env: Record<string, string | undefined> = import.meta.env): AgentApi {
  const useMock = (env.VITE_USE_MOCK ?? "true").toLowerCase() !== "false";
  if (useMock) return new MockAgentApi();
  return new HttpAgentApi({ baseUrl: env.VITE_API_BASE_URL || "http://localhost:8000/api" });
}

export * from "./types";
export { ApiError, describeError } from "./errors";
