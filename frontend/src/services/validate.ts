// Structural checks for API responses (docs/api-contracts.md). A 2xx body that doesn't have the
// contract's shape is reported as `invalid_response` instead of breaking the UI later.
//
// Enum values (task and run statuses) are only checked to be strings: a newer backend may add a
// status, and the UI shows it as "unknown" rather than rejecting the whole response.

type Obj = Record<string, unknown>;

const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const isInt = (v: unknown) => typeof v === "number" && Number.isInteger(v);
const isNum = (v: unknown) => typeof v === "number" && Number.isFinite(v);
const isStr = (v: unknown) => typeof v === "string";
const optStr = (v: unknown) => v === undefined || v === null || typeof v === "string";
const listOf = (v: unknown, item: (x: unknown) => boolean) => Array.isArray(v) && v.every(item);

export const isHealth = (v: unknown) => isObj(v) && isStr(v.status);

export const isProject = (v: unknown) =>
  isObj(v) && isInt(v.id) && isStr(v.name) && isStr(v.created_at);

export const isProjectCreated = (v: unknown) => isProject(v) && isInt((v as Obj).session_id);

export const isProjectList = (v: unknown) => listOf(v, isProject);

const isTask = (v: unknown) =>
  isObj(v) && isInt(v.id) && isInt(v.project_id) && isStr(v.status) && isStr(v.prompt);

const isPendingAction = (v: unknown) =>
  isObj(v) && isInt(v.id) && isInt(v.task_id) && isStr(v.command) && isStr(v.command_hash);

export const isProjectState = (v: unknown) =>
  isObj(v) &&
  isInt(v.project_id) &&
  isStr(v.status) &&
  listOf(v.tasks, isTask) &&
  (v.pending_action === undefined || v.pending_action === null || isPendingAction(v.pending_action));

/** POST /chat and the approve/reject calls: the project state plus a sentence for the chat. */
export const isStateWithMessage = (v: unknown) => isProjectState(v) && isStr((v as Obj).message);

const isLogEntry = (v: unknown) =>
  isObj(v) &&
  isInt(v.id) &&
  isInt(v.task_id) &&
  isStr(v.command) &&
  isStr(v.status) &&
  isStr(v.stdout) &&
  isStr(v.stderr) &&
  isNum(v.duration_ms) &&
  isNum(v.retry_count) &&
  isStr(v.created_at);

export const isLogsPage = (v: unknown) =>
  isObj(v) && isInt(v.project_id) && listOf(v.entries, isLogEntry) && isInt(v.next_after_id);

const isFileInfo = (v: unknown) => isObj(v) && isStr(v.path) && isNum(v.size);

export const isFileList = (v: unknown) =>
  isObj(v) && isInt(v.project_id) && listOf(v.files, isFileInfo) && typeof v.truncated === "boolean";

export const isFileContent = (v: unknown) =>
  isObj(v) && isStr(v.path) && isNum(v.size) && isStr(v.content);

export const isPreviewInfo = (v: unknown) => isObj(v) && isInt(v.project_id) && isStr(v.status) && optStr(v.url);
