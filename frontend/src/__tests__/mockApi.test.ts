import { describe, expect, it } from "vitest";
import { createApi } from "../services";
import { MockAgentApi, fakePlan } from "../services/mockApi";

describe("MockAgentApi (Sprint 1 fake backend)", () => {
  it("mirrors Bejan's fake planner", () => {
    expect(fakePlan("Create a blog")).toEqual(["create project", "create index.html"]);
  });

  it("runs the Sprint 1 flow: create project → chat → two completed tasks", async () => {
    const api = new MockAgentApi(0);
    const project = await api.createProject("Blog");
    expect(project).toMatchObject({ id: 1, name: "Blog", session_id: 1 });

    expect((await api.getTasks(project.id)).status).toBe("idle");

    const res = await api.sendChat(project.id, "Create a blog");
    expect(res.status).toBe("completed");
    expect(res.message).toBe("Finished 2 task(s).");
    expect(res.tasks.map((t) => [t.prompt, t.status])).toEqual([
      ["create project", "succeeded"],
      ["create index.html", "succeeded"],
    ]);

    const state = await api.getTasks(project.id);
    expect(state.tasks).toHaveLength(2);
  });

  it("keeps projects separate", async () => {
    const api = new MockAgentApi(0);
    const a = await api.createProject("A");
    const b = await api.createProject("B");
    await api.sendChat(a.id, "Create a blog");
    expect((await api.getTasks(b.id)).tasks).toHaveLength(0);
  });

  it("rejects unknown projects like the API does", async () => {
    const api = new MockAgentApi(0);
    await expect(api.sendChat(42, "hi")).rejects.toMatchObject({ status: 404, code: "project_not_found" });
  });
});

describe("createApi", () => {
  it("defaults to the mock in Sprint 1", () => {
    expect(createApi({}).mode).toBe("mock");
  });

  it("uses the live API when VITE_USE_MOCK=false", () => {
    expect(createApi({ VITE_USE_MOCK: "false" }).mode).toBe("live");
  });
});
