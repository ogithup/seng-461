import { ChatPanel } from "../components/ChatPanel";
import { ProjectForm } from "../components/ProjectForm";
import { StatusPanel } from "../components/StatusPanel";
import { useAgentSession } from "../hooks/useAgentSession";
import type { AgentApi } from "../services/types";

export function WorkspacePage({ api }: { api: AgentApi }) {
  const session = useAgentSession(api);
  const { project, state } = session;

  const blockedReason = state?.pending_action
    ? "Approve or reject the pending command first"
    : undefined;

  return (
    <div className="app">
      <header className="topbar">
        <h1>AI Website Agent</h1>
        <span className={`mode mode-${api.mode}`} title="Set VITE_USE_MOCK in frontend/.env.local">
          {api.mode === "mock" ? "Mock API" : "Live API"}
        </span>
        {project && (
          <span className="project-name">
            Project: <strong>{project.name}</strong>
          </span>
        )}
      </header>

      {session.error && (
        <div className="error-banner" role="alert">
          {session.error}
        </div>
      )}

      {!project ? (
        <main className="center">
          <ProjectForm onCreate={session.createProject} busy={session.creating} />
        </main>
      ) : (
        <main className="workspace">
          <ChatPanel
            messages={session.messages}
            sending={session.sending}
            onSend={session.send}
            blockedReason={blockedReason}
          />
          <StatusPanel state={state} sending={session.sending} />
        </main>
      )}
    </div>
  );
}
