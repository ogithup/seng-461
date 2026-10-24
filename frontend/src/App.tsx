import { useMemo } from "react";
import { WorkspacePage } from "./pages/WorkspacePage";
import { createApi } from "./services";
import type { AgentApi } from "./services/types";

export default function App({ api }: { api?: AgentApi }) {
  const client = useMemo(() => api ?? createApi(), [api]);
  return <WorkspacePage api={client} />;
}
