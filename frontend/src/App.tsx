import { useMemo } from "react";
import { WorkspacePage } from "./pages/WorkspacePage";
import { createApi } from "./services";
import type { AgentApi } from "./services/types";

interface Props {
  /** The API client; defaults to the one VITE_USE_MOCK / VITE_API_BASE_URL select. */
  api?: AgentApi;
  /** How often task status is polled while work runs (tests shorten it). */
  pollIntervalMs?: number;
}

export default function App({ api, pollIntervalMs }: Props) {
  const client = useMemo(() => api ?? createApi(), [api]);
  return <WorkspacePage api={client} pollIntervalMs={pollIntervalMs} />;
}
