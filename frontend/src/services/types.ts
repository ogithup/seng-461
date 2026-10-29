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

/** POST /api/actions/{id}/approve|reject: the project state after the human decision. */
export interface ActionDecisionResponse extends ProjectState {
  action_id: number;
  decision: "approved" | "rejected";
  message: string;
}

export interface FileInfo {
  path: string;
  size: number;
}

/** GET /api/files — every file in the project's workspace. */
export interface FileList {
  project_id: number;
  files: FileInfo[];
  truncated: boolean;
}

/** GET /api/files/content — one UTF-8 text file. */
export interface FileContent {
  project_id: number;
  path: string;
  size: number;
  content: string;
}

/**
 * GET /api/preview. "static" means the workspace has an index.html. The client resolves `url`
 * so it can be used as an iframe `src` directly.
 */
export interface PreviewInfo {
  project_id: number;
  status: "unavailable" | "static";
  url?: string | null;
}

export type ExecutionStatus = "pending_approval" | "succeeded" | "failed" | "rejected" | "expired";

/** One action the system ran (or asked permission to run). `id` only ever grows. */
export interface LogEntry {
  id: number;
  task_id: number;
  command: string;
  status: ExecutionStatus;
  stdout: string;
  stderr: string;
  output_truncated: boolean;
  retry_count: number;
  duration_ms: number;
  reason?: string | null;
  created_at: string;
}

/** GET /api/logs — entries oldest first; pass `next_after_id` back to get only newer ones. */
export interface LogsPage {
  project_id: number;
  entries: LogEntry[];
  next_after_id: number;
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
  /** `commandHash` is `pending_action.command_hash`: proof the human saw this exact command. */
  approveAction(actionId: number, commandHash: string): Promise<ActionDecisionResponse>;
  rejectAction(actionId: number, commandHash: string): Promise<ActionDecisionResponse>;
  getLogs(projectId: number, afterId?: number, limit?: number): Promise<LogsPage>;
  listFiles(projectId: number): Promise<FileList>;
  getFileContent(projectId: number, path: string): Promise<FileContent>;
  getPreview(projectId: number): Promise<PreviewInfo>;
}

// Limits from backend/api/schemas (chat.py, projects.py). Checked client-side for fast feedback;
// the server still validates.
export const MAX_MESSAGE_LENGTH = 4000;
export const MAX_PROJECT_NAME_LENGTH = 100;
// GET /api/logs accepts limit 1..500 (backend/api/routes/logs.py).
export const MAX_LOG_PAGE = 500;
