import { ChatPanel } from "../components/ChatPanel";
import { FilesPanel } from "../components/FilesPanel";
import { LogsPanel } from "../components/LogsPanel";
import { PreviewPanel } from "../components/PreviewPanel";
import { ProjectForm } from "../components/ProjectForm";
import { ProjectList } from "../components/ProjectList";
import { ProjectSelector } from "../components/ProjectSelector";
import { StatusPanel } from "../components/StatusPanel";
import { stateStamp, useAgentSession } from "../hooks/useAgentSession";
import { useExecutionLogs } from "../hooks/useExecutionLogs";
import { usePreview } from "../hooks/usePreview";
import { useProjectFiles } from "../hooks/useProjectFiles";
import type { AgentApi } from "../services/types";

export function WorkspacePage({ api }: { api: AgentApi }) {
  const session = useAgentSession(api);
  const { project, state } = session;
  const busy = session.sending || session.deciding || state?.status === "running";

  // Panels load once the project's state has, and refetch when it changes (a task finished,
  // an approval appeared...). `state` only ever belongs to the open project.
  const projectId = state?.project_id ?? null;
  const stamp = stateStamp(state);
  const logs = useExecutionLogs(api, projectId, stamp);
  const files = useProjectFiles(api, projectId, stamp);
  const { preview, reload } = usePreview(api, projectId, stamp, busy);

  const blockedReason = state?.pending_action
    ? "Approve or reject the pending command first"
    : undefined;
  const emptyHint =
    state && state.tasks.length > 0
      ? "Earlier messages aren't saved, but this project's tasks, files and log are shown here. Send a new request to continue."
      : undefined;

  return (
    <div className="app">
      <header className="topbar">
        <h1>AI Website Agent</h1>
        <span className={`mode mode-${api.mode}`} title="Set VITE_USE_MOCK in frontend/.env.local">
          {api.mode === "mock" ? "Mock API" : "Live API"}
        </span>
        {project && (
          <ProjectSelector
            projects={session.projects}
            current={project}
            onOpen={session.openProject}
            onNew={session.closeProject}
          />
        )}
      </header>

      {session.error && (
        <div className="error-banner" role="alert">
          <span>{session.error}</span>
          <button type="button" className="link" onClick={session.dismissError}>
            Dismiss
          </button>
        </div>
      )}

      {!project ? (
        <main className="center">
          <div className="start">
            <ProjectForm onCreate={session.createProject} busy={session.creating} />
            <ProjectList
              projects={session.projects}
              loading={session.loadingProjects}
              onOpen={session.openProject}
            />
          </div>
        </main>
      ) : (
        <main className="workspace" aria-busy={session.opening}>
          <ChatPanel
            messages={session.messages}
            sending={session.sending}
            onSend={session.send}
            blockedReason={blockedReason}
            emptyHint={emptyHint}
          />
          <StatusPanel
            state={state}
            sending={session.sending}
            deciding={session.deciding}
            onApprove={session.approve}
            onReject={session.reject}
          />
          <PreviewPanel preview={preview} busy={busy} onReload={reload} />
          <FilesPanel files={files} />
          <LogsPanel entries={logs.entries} error={logs.error} />
        </main>
      )}
    </div>
  );
}
