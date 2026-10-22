import { ApiError } from "./errors";
import type { AgentApi, ChatResponse, Project, ProjectCreated, ProjectState, Task } from "./types";

/**
 * Sprint 1 fake backend, in the browser. It follows the same contract as the real API
 * (docs/api-contracts.md) and mirrors Bejan's fake planner, so swapping to the live API
 * changes nothing in the UI. Nothing here runs a command or calls a model.
 */
export function fakePlan(_request: string): string[] {
  return ["create project", "create index.html"];
}

export class MockAgentApi implements AgentApi {
  readonly mode = "mock" as const;
  private projects: Project[] = [];
  private tasks: Task[] = [];
  private nextProjectId = 1;
  private nextSessionId = 1;
  private nextTaskId = 1;

  constructor(private readonly latencyMs = 400) {}

  async health() {
    await this.delay();
    return { status: "ok" };
  }

  async createProject(name: string): Promise<ProjectCreated> {
    await this.delay();
    const trimmed = name.trim();
    if (!trimmed) throw validation("body.name", "String should have at least 1 character");
    const project: Project = {
      id: this.nextProjectId++,
      name: trimmed,
      created_at: new Date().toISOString(),
    };
    this.projects.push(project);
    return { ...project, session_id: this.nextSessionId++ };
  }

  async listProjects() {
    await this.delay();
    return this.projects.map((p) => ({ ...p }));
  }

  async sendChat(projectId: number, message: string): Promise<ChatResponse> {
    await this.delay();
    this.requireProject(projectId);
    if (!message.trim()) throw validation("body.message", "String should have at least 1 character");

    for (const step of fakePlan(message)) {
      this.tasks.push({
        id: this.nextTaskId++,
        project_id: projectId,
        type: "step",
        status: "succeeded",
        prompt: step,
      });
    }
    const state = this.state(projectId);
    const done = state.tasks.filter((t) => t.status === "succeeded").length;
    return { ...state, message: `Finished ${done} task(s).` };
  }

  async getTasks(projectId: number) {
    await this.delay();
    this.requireProject(projectId);
    return this.state(projectId);
  }

  private state(projectId: number): ProjectState {
    const tasks = this.tasks.filter((t) => t.project_id === projectId).map((t) => ({ ...t }));
    const last = tasks[tasks.length - 1];
    const status = !last ? "idle" : last.status === "succeeded" ? "completed" : "running";
    return { project_id: projectId, status, tasks, pending_action: null };
  }

  private requireProject(projectId: number) {
    if (!this.projects.some((p) => p.id === projectId)) {
      throw new ApiError(404, {
        code: "project_not_found",
        message: "Project not found.",
        project_id: projectId,
      });
    }
  }

  private delay() {
    return new Promise<void>((r) => setTimeout(r, this.latencyMs));
  }
}

function validation(field: string, message: string) {
  return new ApiError(422, {
    code: "validation_error",
    message: "Request validation failed.",
    details: [{ field, message, type: "string_too_short" }],
  });
}
