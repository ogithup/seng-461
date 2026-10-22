import { useCallback, useEffect, useRef, useState } from "react";
import { describeError } from "../services/errors";
import type { AgentApi, ProjectCreated, ProjectState } from "../services/types";

export interface ChatMessage {
  id: number;
  role: "user" | "agent" | "error";
  text: string;
}

export const POLL_INTERVAL_MS = 1500;

/**
 * State for one project's conversation. The API returns the full task list on every call,
 * so the UI simply replaces `state` instead of merging. While the agent is running we poll
 * GET /tasks (the API has no push channel yet).
 */
export function useAgentSession(api: AgentApi) {
  const [project, setProject] = useState<ProjectCreated | null>(null);
  const [state, setState] = useState<ProjectState | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [creating, setCreating] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nextId = useRef(1);

  const push = useCallback((role: ChatMessage["role"], text: string) => {
    setMessages((m) => [...m, { id: nextId.current++, role, text }]);
  }, []);

  const createProject = useCallback(
    async (name: string) => {
      setCreating(true);
      setError(null);
      try {
        const created = await api.createProject(name);
        setProject(created);
        setMessages([]);
        setState(await api.getTasks(created.id));
      } catch (err) {
        setError(describeError(err));
      } finally {
        setCreating(false);
      }
    },
    [api],
  );

  const send = useCallback(
    async (text: string) => {
      if (!project) return false;
      const message = text.trim();
      if (!message) return false;
      setSending(true);
      setError(null);
      push("user", message);
      try {
        const res = await api.sendChat(project.id, message);
        const { message: reply, ...next } = res;
        setState(next);
        push("agent", reply);
        return true;
      } catch (err) {
        push("error", describeError(err));
        return false;
      } finally {
        setSending(false);
      }
    },
    [api, project, push],
  );

  const refresh = useCallback(async () => {
    if (!project) return;
    try {
      setState(await api.getTasks(project.id));
    } catch (err) {
      setError(describeError(err));
    }
  }, [api, project]);

  // Poll while the agent is working; stop as soon as it finishes, fails or waits for a human.
  const running = state?.status === "running";
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(refresh, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [running, refresh]);

  return { project, state, messages, creating, sending, error, createProject, send, refresh };
}
