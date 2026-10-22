// Types mirror docs/api-contracts.md and backend/api/schemas/*.py.
// The frontend never imports backend code; this file is the only copy of the contract here.

export type RunStatus =
  | "idle"
  | "running"
  | "waiting_for_approval"
  | "completed"
  | "failed"
  | "cancelled";

export type TaskStatus =
  | "pending"
  | "running"
  | "waiting_for_approval"
  | "succeeded"
  | "failed"
  | "skipped"
  | "cancelled";

export interface Project {
  id: number;
  name: string;
  created_at: string;
}

export interface ProjectCreated extends Project {
  session_id: number;
}

export interface Task {
  id: number;
  project_id: number;
  type: string;
  status: TaskStatus;
  prompt: string;
}

export interface PendingAction {
  id: number;
  task_id: number;
  command: string;
  command_hash: string;
  reason?: string | null;
  created_at: string;
  expires_at: string;
}

/** GET /api/tasks — everything the UI needs to redraw. `tasks` is always the full list. */
export interface ProjectState {
  project_id: number;
  status: RunStatus;
  tasks: Task[];
  pending_action?: PendingAction | null;
}

/** POST /api/chat adds a human-readable message to the project state. */
export interface ChatResponse extends ProjectState {
  message: string;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  retryable?: boolean;
  project_id?: number;
  request_id?: string;
  details?: { field: string; message: string; type: string }[];
}

/** The client surface the UI depends on. Both the real and the mock client implement it. */
export interface AgentApi {
  readonly mode: "mock" | "live";
  health(): Promise<{ status: string }>;
  createProject(name: string): Promise<ProjectCreated>;
  listProjects(): Promise<Project[]>;
  sendChat(projectId: number, message: string): Promise<ChatResponse>;
  getTasks(projectId: number): Promise<ProjectState>;
}

// Limits from backend/api/schemas (chat.py, projects.py). Checked client-side for fast feedback;
// the server still validates.
export const MAX_MESSAGE_LENGTH = 4000;
export const MAX_PROJECT_NAME_LENGTH = 100;
