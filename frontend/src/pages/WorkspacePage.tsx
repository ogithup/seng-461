import { ChatPanel } from "../components/ChatPanel";
import { FilesPanel } from "../components/FilesPanel";
import { LogsPanel } from "../components/LogsPanel";
import { PreviewPanel, type PreviewNote } from "../components/PreviewPanel";
import { ProjectForm } from "../components/ProjectForm";
import { ProjectList } from "../components/ProjectList";
import { ProjectSelector } from "../components/ProjectSelector";
import { StatusPanel } from "../components/StatusPanel";
import { stateStamp, useAgentSession, type SessionOptions } from "../hooks/useAgentSession";
import { useBackendHealth, type Health } from "../hooks/useBackendHealth";
import { useExecutionLogs } from "../hooks/useExecutionLogs";
import { usePreview } from "../hooks/usePreview";
import { useProjectFiles } from "../hooks/useProjectFiles";
import type { AgentApi, RunStatus } from "../services/types";
import { summarizeRequest, type RequestSummary } from "../utils/requestSummary";

/** What the preview needs to say about the run that produced (or failed to produce) it. */
function previewNotes(summary: RequestSummary | null, runStatus: RunStatus | undefined) {
  let note: PreviewNote | null = null;
  let emptyText: string | undefined;
  const generationFailed = summary ? summary.kind === "failed" && summary.total > 0 : runStatus === "failed";
  if (generationFailed) {
    note = { tone: "bad", text: "The last run failed, so this preview may be incomplete or out of date." };
    emptyText = "No preview: the last run failed before an index.html was written.";
  } else if (summary && (summary.kind === "failed" || summary.kind === "interrupted")) {
    note = { tone: "muted", text: "Your last request wasn't applied. This is the site from an earlier request." };
  }
  return { note, emptyText };
}

function ModeBadge({ api, health, onRecheck }: { api: AgentApi; health: Health; onRecheck: () => void }) {
  if (api.mode === "mock") {
    return (
      <span className="mode mode-mock" title="Set VITE_USE_MOCK=false (or run `npm run dev:live`) to use the backend">
        Mock API
      </span>
    );
  }
  const text = { checking: "checking…", ok: "connected", down: "unreachable" }[health.status];
  return (
    <span className="mode-group">
      <span
        className={`mode mode-live health-${health.status}`}
        title={health.status === "down" ? `${api.target}: ${health.message}` : api.target}
        data-testid="api-mode"
      >
        Live API · {text}
      </span>
      {health.status === "down" && (
        <button type="button" className="link small" onClick={onRecheck}>
          Retry
        </button>
      )}
    </span>
  );
}

export function WorkspacePage({ api, ...options }: { api: AgentApi } & SessionOptions) {
  const session = useAgentSession(api, options);
  const { project, state, request } = session;
  const { health, recheck } = useBackendHealth(api);
  const busy = session.sending || session.deciding || state?.status === "running";
  const mock = api.mode === "mock";

  // Panels load once the project's state has, and refetch when it changes (a task finished,
  // an approval appeared...). `state` only ever belongs to the open project.
  const projectId = state?.project_id ?? null;
  const stamp = stateStamp(state);
  const logs = useExecutionLogs(api, projectId, stamp);
  const files = useProjectFiles(api, projectId, stamp);
  const { preview, reload } = usePreview(api, projectId, stamp, busy);

  const summary = request ? summarizeRequest(request, state, logs.entries) : null;
  const { note, emptyText } = previewNotes(summary, state?.status);

  const blockedReason = !state
    ? "Loading the project…"
    : state.pending_action
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
        <ModeBadge api={api} health={health} onRecheck={recheck} />
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
            request={request}
            summary={summary}
            logs={logs.entries}
            deciding={session.deciding}
            syncError={session.syncError}
            onApprove={session.approve}
            onReject={session.reject}
          />
          <PreviewPanel
            preview={preview}
            busy={busy}
            note={note}
            emptyText={emptyText}
            mock={mock}
            onReload={reload}
          />
          <FilesPanel files={files} mock={mock} />
          <LogsPanel entries={logs.entries} error={logs.error} />
        </main>
      )}
    </div>
  );
}
