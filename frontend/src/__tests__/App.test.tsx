import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import App from "../App";
import { PROJECT_STORAGE_KEY } from "../hooks/useAgentSession";
import { ApiError } from "../services/errors";
import { MockAgentApi } from "../services/mockApi";
import type { ChatResponse, ProjectState } from "../services/types";

type User = ReturnType<typeof userEvent.setup>;

async function startProject(name = "Blog") {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Project name"), name);
  await user.click(screen.getByRole("button", { name: "Create project" }));
  await screen.findByLabelText("Message to the agent");
  return user;
}

async function send(user: User, text: string, reply: string | RegExp) {
  await user.type(screen.getByLabelText("Message to the agent"), text);
  await user.click(screen.getByRole("button", { name: "Send" }));
  await screen.findByText(reply);
}

const region = (name: string) => screen.getByRole("region", { name });

describe("App — chat and status", () => {
  it("shows chat input, send button and status panel after creating a project", async () => {
    render(<App api={new MockAgentApi(0)} />);
    await startProject();

    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(screen.getByTestId("run-status")).toHaveTextContent("Idle");
    expect(screen.getByText("No tasks yet.")).toBeInTheDocument();
    expect(screen.getByLabelText("Project")).toHaveDisplayValue("Blog");
  });

  it("sends “Create a blog” and displays the returned tasks", async () => {
    render(<App api={new MockAgentApi(0)} />);
    const user = await startProject();

    await send(user, "Create a blog", "Finished 3 task(s).");

    const status = region("Agent status");
    expect(within(status).getByTestId("run-status")).toHaveTextContent("Completed");
    expect(within(status).getByText('Write index.html (blog site "My Blog")')).toBeInTheDocument();
    expect(within(status).getAllByText("Completed")).toHaveLength(4); // run + 3 tasks
    expect(within(status).getByText("3/3 tasks done")).toBeInTheDocument();
    expect(screen.getByLabelText("Message to the agent")).toHaveValue("");
  });

  it("sends with Enter and keeps the text when the request fails", async () => {
    const api = new MockAgentApi(0);
    vi.spyOn(api, "sendChat").mockRejectedValue(
      new ApiError(409, { code: "project_busy", message: "busy", retryable: true }),
    );
    render(<App api={api} />);
    const user = await startProject();

    await user.type(screen.getByLabelText("Message to the agent"), "Create a blog{Enter}");

    expect(await screen.findByText(/still working on this project/)).toBeInTheDocument();
    expect(screen.getByLabelText("Message to the agent")).toHaveValue("Create a blog");
  });

  it("shows a dismissible error banner when the backend is unreachable", async () => {
    const api = new MockAgentApi(0);
    vi.spyOn(api, "createProject").mockRejectedValue(
      new ApiError(0, { code: "network_error", message: "Network error" }),
    );
    render(<App api={api} />);
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Project name"), "Blog");
    await user.click(screen.getByRole("button", { name: "Create project" }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/Can't reach the backend/));
    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows each task's progress while a request is still running", async () => {
    const api = new MockAgentApi(0);
    render(<App api={api} />);
    const user = await startProject();
    const step = (id: number, status: "succeeded" | "running", prompt: string) => ({
      id, project_id: 1, type: "step", status, prompt,
    });
    const running: ProjectState = {
      project_id: 1,
      status: "running",
      tasks: [step(1, "succeeded", "Write index.html"), step(2, "running", "Write style.css")],
      pending_action: null,
    };
    let finish!: (res: ChatResponse) => void;
    vi.spyOn(api, "sendChat").mockImplementation(() => new Promise((r) => (finish = r)));
    vi.spyOn(api, "getTasks").mockResolvedValue(running);

    await user.type(screen.getByLabelText("Message to the agent"), "Create a blog{Enter}");

    const status = region("Agent status");
    expect(await within(status).findByText("1/2 tasks done", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(within(status).getByText("Running")).toBeInTheDocument();
    expect(within(region("Preview")).getByText(/building the site/)).toBeInTheDocument();

    const done = running.tasks.map((t) => ({ ...t, status: "succeeded" as const }));
    act(() => finish({ ...running, status: "completed", tasks: done, message: "Finished 2 task(s)." }));
    expect(await within(status).findByText("2/2 tasks done")).toBeInTheDocument();
  });
});

describe("App — projects", () => {
  it("reopens the open project after a page refresh", async () => {
    const api = new MockAgentApi(0);
    const { unmount } = render(<App api={api} />);
    const user = await startProject("Blog");
    await send(user, "Create a blog", "Finished 3 task(s).");
    unmount();

    render(<App api={api} />); // same backend, fresh page

    expect(await screen.findByLabelText("Project")).toHaveDisplayValue("Blog");
    expect(await within(region("Agent status")).findByText("3/3 tasks done")).toBeInTheDocument();
    expect(screen.getByText(/Earlier messages aren't saved/)).toBeInTheDocument();
    expect(await within(region("Generated files")).findByText("index.html")).toBeInTheDocument();
  });

  it("switches between projects with the selector and the start screen", async () => {
    render(<App api={new MockAgentApi(0)} />);
    let user = await startProject("First");
    await send(user, "Create a blog", "Finished 3 task(s).");

    await user.click(screen.getByRole("button", { name: "New project" }));
    expect(within(region("Existing projects")).getByRole("button", { name: "First" })).toBeInTheDocument();
    user = await startProject("Second");
    expect(screen.getByText("No tasks yet.")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Project"), "First");
    expect(await within(region("Agent status")).findByText("3/3 tasks done")).toBeInTheDocument();
    expect(screen.getByText("Finished 3 task(s).")).toBeInTheDocument(); // its chat came back too

    await user.click(screen.getByRole("button", { name: "New project" }));
    await user.click(within(region("Existing projects")).getByRole("button", { name: "Second" }));
    expect(await screen.findByLabelText("Project")).toHaveDisplayValue("Second");
    expect(await screen.findByText("No tasks yet.")).toBeInTheDocument();
  });

  it("forgets a remembered project that no longer exists", async () => {
    window.localStorage.setItem(PROJECT_STORAGE_KEY, "99");
    render(<App api={new MockAgentApi(0)} />);

    expect(await screen.findByText("No projects yet.")).toBeInTheDocument();
    expect(window.localStorage.getItem(PROJECT_STORAGE_KEY)).toBeNull();
  });
});

describe("App — files, preview and log", () => {
  it("lists generated files and shows one on click", async () => {
    render(<App api={new MockAgentApi(0)} />);
    const user = await startProject();
    expect(within(region("Generated files")).getByText("No files generated yet.")).toBeInTheDocument();

    await send(user, "Create a blog", "Finished 3 task(s).");

    const files = region("Generated files");
    await user.click(await within(files).findByRole("button", { name: /index\.html/ }));
    expect(await within(files).findByLabelText("Contents of index.html")).toHaveTextContent(
      "<title>Home · My Blog</title>",
    );
    await user.click(within(files).getByRole("button", { name: "Close" }));
    expect(within(files).queryByLabelText("Contents of index.html")).not.toBeInTheDocument();
  });

  it("goes from an empty preview to a sandboxed frame of the site", async () => {
    render(<App api={new MockAgentApi(0)} />);
    const user = await startProject();
    expect(await screen.findByText(/No preview yet/)).toBeInTheDocument();

    await send(user, "Create a blog", "Finished 3 task(s).");

    const frame = await screen.findByTitle("Website preview");
    expect(frame).toHaveAttribute("sandbox", "allow-scripts");
    expect(frame.getAttribute("src")).toMatch(/^data:text\/html/);
  });

  it("shows a preview error and recovers on retry", async () => {
    const api = new MockAgentApi(0);
    const getPreview = vi
      .spyOn(api, "getPreview")
      .mockRejectedValueOnce(new ApiError(0, { code: "network_error", message: "Network error" }));
    render(<App api={api} />);
    const user = await startProject();

    const preview = region("Preview");
    expect(await within(preview).findByText(/Couldn't load the preview/)).toBeInTheDocument();
    await user.click(within(preview).getByRole("button", { name: "Try again" }));
    expect(await within(preview).findByText(/No preview yet/)).toBeInTheDocument();
    expect(getPreview).toHaveBeenCalledTimes(2);
  });

  it("logs every file write", async () => {
    render(<App api={new MockAgentApi(0)} />);
    const user = await startProject();
    expect(within(region("Execution log")).getByText("Nothing has run yet.")).toBeInTheDocument();

    await send(user, "Create a blog", "Finished 3 task(s).");

    const log = region("Execution log");
    expect(await within(log).findByText("write_file style.css")).toBeInTheDocument();
    expect(within(log).getByText("wrote index.html", { exact: false })).toBeInTheDocument();
    expect(within(log).getAllByText("Succeeded")).toHaveLength(3);
  });
});

describe("App — approvals", () => {
  it("rejects a pending command and blocks chat until then", async () => {
    render(<App api={new MockAgentApi(0)} />);
    const user = await startProject();
    await send(user, "run npm install", "I need your approval to run: npm install");

    const card = screen.getByRole("group", { name: "Approval required" });
    expect(within(card).getByText("npm install")).toBeInTheDocument();
    expect(screen.getByTestId("run-status")).toHaveTextContent("Awaiting approval");
    expect(screen.getByLabelText("Message to the agent")).toBeDisabled();
    expect(await within(region("Execution log")).findByText("Awaiting approval")).toBeInTheDocument();

    await user.click(within(card).getByRole("button", { name: "Reject" }));

    expect(await screen.findByText("Cancelled: 0 task(s) done before it stopped.")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Approval required" })).not.toBeInTheDocument();
    expect(screen.getByTestId("run-status")).toHaveTextContent("Cancelled");
    expect(screen.getByLabelText("Message to the agent")).toBeEnabled();
    expect(await within(region("Execution log")).findByText("Rejected")).toBeInTheDocument();
  });

  it("approves with the command's hash and reports the failure", async () => {
    const api = new MockAgentApi(0);
    const approve = vi.spyOn(api, "approveAction");
    render(<App api={api} />);
    const user = await startProject();
    await send(user, "run npm install", /I need your approval/);
    const { pending_action } = await api.getTasks(1);

    await user.click(screen.getByRole("button", { name: "Approve" }));

    expect(await screen.findByText(/Stopped after a failure/)).toBeInTheDocument();
    expect(approve).toHaveBeenCalledWith(pending_action!.id, pending_action!.command_hash);
    expect(screen.getByTestId("run-status")).toHaveTextContent("Failed");
    expect(screen.getByText(/The run stopped after a failure/)).toBeInTheDocument();
    const log = region("Execution log");
    expect(await within(log).findByText(/run_command is closed this sprint/)).toBeInTheDocument();
  });

  it("shows why a decision was refused and redraws from the server", async () => {
    const api = new MockAgentApi(0);
    render(<App api={api} />);
    const user = await startProject();
    await send(user, "run npm install", /I need your approval/);
    vi.spyOn(api, "approveAction").mockRejectedValue(
      new ApiError(409, { code: "action_expired", message: "expired" }),
    );
    const getTasks = vi.spyOn(api, "getTasks");

    await user.click(screen.getByRole("button", { name: "Approve" }));

    expect(await screen.findByText(/approval request has expired/)).toBeInTheDocument();
    await waitFor(() => expect(getTasks).toHaveBeenCalled());
  });
});
