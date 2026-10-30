import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, describeError } from "../services/errors";
import type { AgentApi, Project, ProjectState } from "../services/types";

export interface ChatMessage {
  id: number;
  role: "user" | "agent" | "error";
  text: string;
}

export const POLL_INTERVAL_MS = 1500;
/** localStorage key holding the open project's id, so a page refresh reopens it. */
export const PROJECT_STORAGE_KEY = "ai-website-agent.projectId";

/** Changes whenever something visible in the project state changes; panels refetch on it. */
export function stateStamp(state: ProjectState | null): string {
  if (!state) return "";
  const tasks = state.tasks.map((t) => `${t.id}:${t.status}`).join(",");
  return `${state.project_id}|${state.status}|${tasks}|${state.pending_action?.id ?? ""}`;
}

// Responses that add fields (message, action_id, decision) are narrowed to the state itself.
function toState({ project_id, status, tasks, pending_action }: ProjectState): ProjectState {
  return { project_id, status, tasks, pending_action };
}

function readStoredProjectId(): number | null {
  try {
    const id = Number(window.localStorage.getItem(PROJECT_STORAGE_KEY));
    return Number.isInteger(id) && id > 0 ? id : null;
  } catch {
    return null; // storage disabled
  }
}

function storeProjectId(id: number | null) {
  try {
    if (id === null) window.localStorage.removeItem(PROJECT_STORAGE_KEY);
    else window.localStorage.setItem(PROJECT_STORAGE_KEY, String(id));
  } catch {
    /* storage disabled: the project just won't reopen after a refresh */
  }
}

/**
 * The open project and its conversation. The API returns the full task list on every call,
 * so the UI replaces `state` instead of merging. While a request runs we poll GET /tasks
 * (the API has no push channel yet). Chat history is kept per project for this browser
 * session only; the API does not store messages.
 */
export function useAgentSession(api: AgentApi) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [project, setProject] = useState<Project | null>(null);
  const [state, setState] = useState<ProjectState | null>(null);
  const [history, setHistory] = useState<Record<number, ChatMessage[]>>({});
  const [creating, setCreating] = useState(false);
  const [opening, setOpening] = useState(false);
  const [sending, setSending] = useState(false);
  const [deciding, setDeciding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nextId = useRef(1);
  // The project on screen. Responses for any other project arrive late and are dropped.
  const currentId = useRef<number | null>(null);

  const push = useCallback((projectId: number, role: ChatMessage["role"], text: string) => {
    const message = { id: nextId.current++, role, text };
    setHistory((h) => ({ ...h, [projectId]: [...(h[projectId] ?? []), message] }));
  }, []);

  const applyState = useCallback((projectId: number, next: ProjectState) => {
    if (currentId.current === projectId) setState(toState(next));
  }, []);

  const closeProject = useCallback(() => {
    currentId.current = null;
    storeProjectId(null);
    setProject(null);
    setState(null);
    setOpening(false);
  }, []);

  const openProject = useCallback(
    async (target: Project) => {
      currentId.current = target.id;
      storeProjectId(target.id);
      setProject(target);
      setState(null);
      setOpening(true);
      setError(null);
      try {
        applyState(target.id, await api.getTasks(target.id));
      } catch (err) {
        if (currentId.current !== target.id) return;
        if (err instanceof ApiError && err.code === "project_not_found") {
          closeProject();
          setProjects((list) => list.filter((p) => p.id !== target.id));
        }
        setError(describeError(err));
      } finally {
        if (currentId.current === target.id) setOpening(false);
      }
    },
    [api, applyState, closeProject],
  );

  const loadProjects = useCallback(async () => {
    setLoadingProjects(true);
    try {
      const list = await api.listProjects();
      setProjects(list);
      return list;
    } catch (err) {
      setError(describeError(err));
      return null;
    } finally {
      setLoadingProjects(false);
    }
  }, [api]);

  // On load: list projects and reopen the one that was open before the refresh.
  useEffect(() => {
    let cancelled = false;
    void loadProjects().then((list) => {
      if (cancelled || !list || currentId.current !== null) return;
      const stored = readStoredProjectId();
      const previous = list.find((p) => p.id === stored);
      if (previous) void openProject(previous);
      else if (stored !== null) storeProjectId(null);
    });
    return () => {
      cancelled = true;
    };
  }, [loadProjects, openProject]);

  const createProject = useCallback(
    async (name: string) => {
      setCreating(true);
      setError(null);
      try {
        const { session_id: _, ...created } = await api.createProject(name);
        setProjects((list) => [...list.filter((p) => p.id !== created.id), created]);
        await openProject(created);
      } catch (err) {
        setError(describeError(err));
      } finally {
        setCreating(false);
      }
    },
    [api, openProject],
  );

  const send = useCallback(
    async (text: string) => {
      if (!project) return false;
      const projectId = project.id;
      const message = text.trim();
      if (!message) return false;
      setSending(true);
      setError(null);
      push(projectId, "user", message);
      try {
        const res = await api.sendChat(projectId, message);
        applyState(projectId, res);
        push(projectId, "agent", res.message);
        return true;
      } catch (err) {
        push(projectId, "error", describeError(err));
        return false;
      } finally {
        setSending(false);
      }
    },
    [api, project, push, applyState],
  );

  const refresh = useCallback(async () => {
    const projectId = currentId.current;
    if (projectId === null) return;
    try {
      applyState(projectId, await api.getTasks(projectId));
    } catch (err) {
      if (currentId.current === projectId) setError(describeError(err));
    }
  }, [api, applyState]);

  /**
   * Sends the human's decision on `pending_action`. The server decides what it means; the UI
   * only echoes back the id and `command_hash` of the command it showed.
   */
  const decide = useCallback(
    async (approve: boolean) => {
      const pending = state?.pending_action;
      if (!project || !pending || deciding) return;
      const projectId = project.id;
      setDeciding(true);
      setError(null);
      try {
        const res = approve
          ? await api.approveAction(pending.id, pending.command_hash)
          : await api.rejectAction(pending.id, pending.command_hash);
        applyState(projectId, res);
        push(projectId, "agent", res.message);
      } catch (err) {
        push(projectId, "error", describeError(err));
        // It may have expired or changed: show what the server has now.
        await refresh();
      } finally {
        setDeciding(false);
      }
    },
    [api, project, state, deciding, push, applyState, refresh],
  );
  const approve = useCallback(() => decide(true), [decide]);
  const reject = useCallback(() => decide(false), [decide]);

  // Poll while a request is in flight or the agent is still working; stop as soon as it
  // finishes, fails or waits for a human. Reads don't take the project lock, so polling
  // during POST /chat shows each task as it completes.
  const active = sending || deciding || state?.status === "running";
  useEffect(() => {
    if (!active || !project) return;
    const timer = setInterval(refresh, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [active, project, refresh]);

  return {
    projects,
    loadingProjects,
    project,
    state,
    messages: (project && history[project.id]) || [],
    creating,
    opening,
    sending,
    deciding,
    error,
    dismissError: () => setError(null),
    createProject,
    openProject,
    closeProject,
    send,
    refresh,
    approve,
    reject,
  };
}
