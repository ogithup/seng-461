import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import App from "../App";
import { PROJECT_STORAGE_KEY } from "../hooks/useAgentSession";
import { ApiError } from "../services/errors";
import { MockAgentApi } from "../services/mockApi";
import type { ChatResponse, ProjectState, Task, TaskStatus } from "../services/types";

type User = ReturnType<typeof userEvent.setup>;

// Polling is shortened so state changes show up quickly; the real default is 1.5 s.
const POLL = 20;

async function startProject(name = "Blog") {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Project name"), name);
  await user.click(screen.getByRole("button", { name: "Create project" }));
  await screen.findByLabelText("Message to the agent");
  await waitFor(() => expect(screen.getByLabelText("Message to the agent")).toBeEnabled());
  return user;
}

async function send(user: User, text: string, reply: string | RegExp) {
  await user.type(screen.getByLabelText("Message to the agent"), text);
  await user.click(screen.getByRole("button", { name: "Send" }));
  await within(chat()).findByText(reply);
}

const region = (name: string) => screen.getByRole("region", { name });
const chat = () => screen.getByRole("log");
const latest = () => screen.getByRole("status", { name: "Latest request" });
const requestBadge = () => screen.getByTestId("request-status");

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (err: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const task = (id: number, status: TaskStatus | string, prompt = `Write file${id}.html`): Task =>
  ({ id, project_id: 1, type: "step", status, prompt }) as Task;

const projectState = (status: ProjectState["status"], tasks: Task[]): ProjectState => ({
  project_id: 1,
  status,
  tasks,
  pending_action: null,
});

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
    const api = new MockAgentApi(0);
    const sendChat = vi.spyOn(api, "sendChat");
    render(<App api={api} />);
    const user = await startProject();

    await send(user, "Create a blog", "Finished 3 task(s).");

    expect(sendChat).toHaveBeenCalledWith(1, "Create a blog");
    const status = region("Agent status");
    expect(within(status).getByTestId("run-status")).toHaveTextContent("Completed");
    expect(within(status).getByText('Write index.html (blog site "My Blog")')).toBeInTheDocument();
    expect(within(status).getAllByText("Succeeded")).toHaveLength(4); // request + 3 tasks
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

    expect(await within(chat()).findByText(/still working on this project/)).toBeInTheDocument();
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
    const running = projectState("running", [
      task(1, "succeeded", "Write index.html"),
      task(2, "running", "Write style.css"),
    ]);
    let finish!: (res: ChatResponse) => void;
    vi.spyOn(api, "sendChat").mockImplementation(() => new Promise((r) => (finish = r)));
    vi.spyOn(api, "getTasks").mockResolvedValue(running);

    await user.type(screen.getByLabelText("Message to the agent"), "Create a blog{Enter}");

    const status = region("Agent status");
    expect(await within(status).findByText("1/2 tasks done", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(requestBadge()).toHaveTextContent("Running");
    expect(within(status).getByTestId("run-status")).toHaveTextContent("Running");
    expect(within(region("Preview")).getByText(/building the site/)).toBeInTheDocument();

    const done = running.tasks.map((t) => ({ ...t, status: "succeeded" as const }));
    act(() => finish({ ...running, status: "completed", tasks: done, message: "Finished 2 task(s)." }));
    expect(await within(status).findByText("2/2 tasks done")).toBeInTheDocument();
  });
});

describe("App — task states from the backend (Sprint 4)", () => {
  it("goes Pending → Running → Succeeded, and shows success only once the backend confirms it", async () => {
    const api = new MockAgentApi(0);
    render(<App api={api} pollIntervalMs={POLL} />);
    const user = await startProject();
    let current = projectState("idle", []);
    vi.spyOn(api, "getTasks").mockImplementation(async () => current);
    const reply = deferred<ChatResponse>();
    vi.spyOn(api, "sendChat").mockReturnValue(reply.promise);

    await user.type(screen.getByLabelText("Message to the agent"), "Create a blog{Enter}");

    // Sent, but the backend hasn't created any task yet.
    expect(requestBadge()).toHaveTextContent("Pending");
    expect(within(latest()).getByText(/Waiting for the backend to plan/)).toBeInTheDocument();
    expect(within(latest()).getByLabelText("Generation progress")).not.toHaveAttribute("value");

    current = projectState("running", [task(1, "pending"), task(2, "pending")]);
    expect(await within(latest()).findByText("2 task(s) planned, waiting to start…")).toBeInTheDocument();
    expect(requestBadge()).toHaveTextContent("Pending");
    expect(within(region("Agent status")).getAllByText("Pending")).toHaveLength(3);

    current = projectState("running", [task(1, "succeeded"), task(2, "running")]);
    expect(await within(latest()).findByText("1 of 2 task(s) done…")).toBeInTheDocument();
    expect(requestBadge()).toHaveTextContent("Running");
    const progress = within(latest()).getByLabelText("Generation progress");
    expect(progress).toHaveAttribute("value", "1");
    expect(progress).toHaveAttribute("max", "2");
    expect(within(latest()).queryByText("Succeeded")).not.toBeInTheDocument();

    const finished = projectState("completed", [task(1, "succeeded"), task(2, "succeeded")]);
    current = finished;
    act(() => reply.resolve({ ...finished, message: "Finished 2 task(s)." }));

    expect(await within(latest()).findByText("All 2 task(s) succeeded.")).toBeInTheDocument();
    expect(requestBadge()).toHaveTextContent("Succeeded");
    expect(within(latest()).queryByLabelText("Generation progress")).not.toBeInTheDocument();
  });

  it("shows a failed generation with the backend's reason and the skipped tasks", async () => {
    render(<App api={new MockAgentApi(0)} />);
    const user = await startProject();

    await send(user, "Create a blog (simulate failure)", /Stopped after a failure/);

    expect(requestBadge()).toHaveTextContent("Failed");
    expect(within(latest()).getByText(/“Write about\.html \(blog site "My Blog"\)” failed: Mock failure/)).toBeInTheDocument();
    expect(within(latest()).getByText(/1 later task\(s\) were skipped/)).toBeInTheDocument();
    const status = region("Agent status");
    expect(within(status).getByTestId("run-status")).toHaveTextContent("Failed");
    const failedTask = within(status).getByText('Write about.html (blog site "My Blog")').closest("li")!;
    expect(within(failedTask).getByText(/Mock failure: about\.html was not written/)).toBeInTheDocument();
    const skippedTask = within(status).getByText('Write style.css (blog site "My Blog")').closest("li")!;
    expect(within(skippedTask).getByText("Skipped")).toBeInTheDocument();
    expect(within(skippedTask).getByText("Not run because an earlier task failed.")).toBeInTheDocument();
    expect(within(status).queryByText("Succeeded", { selector: "[data-testid=request-status]" })).toBeNull();

    // index.html was written before the failure: the preview is shown, with a warning.
    const preview = region("Preview");
    expect(await within(preview).findByTitle("Website preview")).toBeInTheDocument();
    expect(within(preview).getByText(/last run failed, so this preview may be incomplete/)).toBeInTheDocument();
  });

  it("shows an unsupported request as failed, not as the earlier success", async () => {
    render(<App api={new MockAgentApi(0)} />);
    const user = await startProject();
    await send(user, "Create a blog", "Finished 3 task(s).");
    expect(requestBadge()).toHaveTextContent("Succeeded");

    await send(user, "Build an online shop", /Online shops are not supported yet/);

    expect(requestBadge()).toHaveTextContent("Failed");
    expect(within(latest()).getByText("“Build an online shop”")).toBeInTheDocument();
    expect(
      within(latest()).getByText("Online shops are not supported yet. Try a blog, portfolio or landing page."),
    ).toBeInTheDocument();
    // The project itself is still what the backend says: the earlier run completed, nothing was added.
    const status = region("Agent status");
    expect(within(status).getByTestId("run-status")).toHaveTextContent("Completed");
    expect(within(status).getByText("3/3 tasks done")).toBeInTheDocument();
    expect(within(region("Preview")).getByText(/Your last request wasn't applied/)).toBeInTheDocument();
    expect(screen.getByLabelText("Message to the agent")).toHaveValue("Build an online shop");
  });

  it("reports a request that never reached the backend as interrupted", async () => {
    const api = new MockAgentApi(0);
    vi.spyOn(api, "sendChat").mockRejectedValue(new ApiError(0, { code: "network_error", message: "x" }));
    render(<App api={api} />);
    const user = await startProject();

    await send(user, "Create a blog", /Can't reach the backend.*latest status from the backend/);

    expect(requestBadge()).toHaveTextContent("Interrupted");
    expect(within(latest()).getByText(/has not confirmed this request/)).toBeInTheDocument();
    expect(within(region("Agent status")).getByTestId("run-status")).toHaveTextContent("Idle");
  });

  it("shows what the backend did when the answer to a request was lost", async () => {
    const api = new MockAgentApi(0);
    const realSend = api.sendChat.bind(api);
    vi.spyOn(api, "sendChat").mockImplementation(async (id, message) => {
      await realSend(id, message); // the backend ran it…
      throw new ApiError(0, { code: "timeout", message: "x" }); // …but the answer never arrived
    });
    render(<App api={api} />);
    const user = await startProject();

    await send(user, "Create a blog", /took too long to answer.*latest status/);

    // GET /tasks afterwards shows the request's tasks, which the backend confirms succeeded.
    expect(await within(latest()).findByText("All 3 task(s) succeeded.")).toBeInTheDocument();
    expect(requestBadge()).toHaveTextContent("Succeeded");
  });

  it("ignores a status check that answers after the final result", async () => {
    const api = new MockAgentApi(0);
    render(<App api={api} pollIntervalMs={POLL} />);
    const user = await startProject();
    const slowPoll = deferred<ProjectState>();
    const getTasks = vi.spyOn(api, "getTasks").mockReturnValue(slowPoll.promise);
    const reply = deferred<ChatResponse>();
    vi.spyOn(api, "sendChat").mockReturnValue(reply.promise);

    await user.type(screen.getByLabelText("Message to the agent"), "Create a blog{Enter}");
    await waitFor(() => expect(getTasks).toHaveBeenCalled()); // a poll is now in flight

    const finished = projectState("completed", [task(1, "succeeded"), task(2, "succeeded")]);
    act(() => reply.resolve({ ...finished, message: "Finished 2 task(s)." }));
    expect(await within(latest()).findByText("All 2 task(s) succeeded.")).toBeInTheDocument();

    // The poll started before that answer and carries older data.
    await act(async () => slowPoll.resolve(projectState("running", [task(1, "succeeded"), task(2, "running")])));

    expect(requestBadge()).toHaveTextContent("Succeeded");
    expect(screen.getByTestId("run-status")).toHaveTextContent("Completed");
    expect(screen.getByText("2/2 tasks done")).toBeInTheDocument();
  });

  it("shows an unrecognised status as unknown, never as success", async () => {
    const api = new MockAgentApi(0);
    render(<App api={api} pollIntervalMs={POLL} />);
    const user = await startProject();
    const odd = projectState("completed", [task(1, "succeeded"), task(2, "queued")]);
    vi.spyOn(api, "getTasks").mockResolvedValue(odd);
    vi.spyOn(api, "sendChat").mockResolvedValue({ ...odd, message: "Done." });

    await send(user, "Create a blog", "Done.");

    expect(requestBadge()).toHaveTextContent("Unknown");
    expect(within(latest()).getByText(/unrecognised task status “queued”/)).toBeInTheDocument();
    expect(within(region("Agent status")).getByText("Unknown (queued)")).toBeInTheDocument();
  });

  it("keeps polling through a failed status check without an error banner", async () => {
    const api = new MockAgentApi(0);
    render(<App api={api} pollIntervalMs={POLL} />);
    const user = await startProject();
    const reply = deferred<ChatResponse>();
    vi.spyOn(api, "sendChat").mockReturnValue(reply.promise);
    const running = projectState("running", [task(1, "running")]);
    vi.spyOn(api, "getTasks")
      .mockRejectedValueOnce(new ApiError(0, { code: "network_error", message: "x" }))
      .mockResolvedValue(running);

    await user.type(screen.getByLabelText("Message to the agent"), "Create a blog{Enter}");

    expect(await screen.findByText(/Status updates paused: Can't reach the backend/)).toBeInTheDocument();
    expect(await within(latest()).findByText("0 of 1 task(s) done…")).toBeInTheDocument();
    expect(screen.queryByText(/Status updates paused/)).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    act(() => reply.resolve({ ...projectState("completed", [task(1, "succeeded")]), message: "Finished 1 task(s)." }));
    expect(await within(latest()).findByText("All 1 task(s) succeeded.")).toBeInTheDocument();
  });

  it("shows Loading until the project's state arrives, and blocks sending meanwhile", async () => {
    const api = new MockAgentApi(0);
    const tasksLoaded = deferred<ProjectState>();
    vi.spyOn(api, "getTasks").mockReturnValue(tasksLoaded.promise);
    render(<App api={api} />);
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Project name"), "Blog");
    await user.click(screen.getByRole("button", { name: "Create project" }));

    expect(await screen.findByText("Loading tasks…")).toBeInTheDocument();
    expect(screen.getByTestId("run-status")).toHaveTextContent("Loading…");
    expect(screen.getByLabelText("Message to the agent")).toBeDisabled();
    expect(screen.getByLabelText("Message to the agent")).toHaveAttribute("placeholder", "Loading the project…");

    await act(async () => tasksLoaded.resolve(projectState("idle", [])));
    expect(screen.getByTestId("run-status")).toHaveTextContent("Idle");
    expect(screen.getByLabelText("Message to the agent")).toBeEnabled();
  });

  it("hides the agent's internal token in task prompts but keeps it in the tooltip", async () => {
    const api = new MockAgentApi(0);
    await api.createProject("Blog");
    window.localStorage.setItem(PROJECT_STORAGE_KEY, "1"); // reopened on load
    const prompt = 'Write index.html (blog site "X") [delta:eJyrVkrLz1eyUlAqSa0oUbJSSs7PS8tMLy1OVaoFAIj_Cbk]';
    vi.spyOn(api, "getTasks").mockResolvedValue(projectState("completed", [task(1, "succeeded", prompt)]));

    render(<App api={api} />);

    const label = await screen.findByText('Write index.html (blog site "X")');
    expect(label).toHaveAttribute("title", prompt);
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

  it("explains files that can't be shown instead of showing them", async () => {
    const api = new MockAgentApi(0);
    render(<App api={api} />);
    const user = await startProject();
    await send(user, "Create a blog", "Finished 3 task(s).");
    vi.spyOn(api, "getFileContent")
      .mockRejectedValueOnce(new ApiError(415, { code: "unsupported_file_type", message: "x" }))
      .mockRejectedValueOnce(new ApiError(404, { code: "file_not_found", message: "x" }));

    const files = region("Generated files");
    await user.click(await within(files).findByRole("button", { name: /style\.css/ }));
    expect(await within(files).findByText("Only text files can be shown here.")).toBeInTheDocument();
    await user.click(within(files).getByRole("button", { name: /about\.html/ }));
    expect(await within(files).findByText("That file is no longer in the project.")).toBeInTheDocument();
    expect(within(files).queryByLabelText(/Contents of/)).not.toBeInTheDocument();
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

  it("says why there is no preview when the run failed before index.html", async () => {
    const api = new MockAgentApi(0);
    render(<App api={api} />);
    const user = await startProject();
    vi.spyOn(api, "getPreview").mockResolvedValue({ project_id: 1, status: "unavailable", url: null });

    await send(user, "Create a blog (simulate failure)", /Stopped after a failure/);

    expect(
      await within(region("Preview")).findByText("No preview: the last run failed before an index.html was written."),
    ).toBeInTheDocument();
    expect(screen.queryByTitle("Website preview")).not.toBeInTheDocument();
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

  it("keeps panels steady while a background refresh is pending", async () => {
    const api = new MockAgentApi(0);
    render(<App api={api} />);
    const user = await startProject();
    expect(await screen.findByText(/No preview yet/)).toBeInTheDocument();
    expect(await screen.findByText("No files generated yet.")).toBeInTheDocument();
    const never = () => new Promise<never>(() => {});
    vi.spyOn(api, "getPreview").mockImplementation(never);
    vi.spyOn(api, "listFiles").mockImplementation(never);

    await send(user, "run npm install", /I need your approval/); // state changes → refetch

    expect(within(region("Preview")).getByText(/No preview yet/)).toBeInTheDocument();
    expect(within(region("Generated files")).getByText("No files generated yet.")).toBeInTheDocument();
    expect(screen.queryByText(/Loading (preview|files)/)).not.toBeInTheDocument();
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

  it("labels the mock's files and preview as mock data", async () => {
    render(<App api={new MockAgentApi(0)} />);
    await startProject();

    expect(screen.getByText("Mock API")).toBeInTheDocument();
    expect(within(region("Generated files")).getByText(/these files are made in the browser, not by the backend/)).toBeInTheDocument();
    expect(within(region("Preview")).getByText(/this site is made in the browser, not by the backend/)).toBeInTheDocument();
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
    expect(requestBadge()).toHaveTextContent("Awaiting approval");
    expect(screen.getByLabelText("Message to the agent")).toBeDisabled();
    expect(await within(region("Execution log")).findByText("Awaiting approval")).toBeInTheDocument();

    await user.click(within(card).getByRole("button", { name: "Reject" }));

    expect(await screen.findByText("Cancelled: 0 task(s) done before it stopped.")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Approval required" })).not.toBeInTheDocument();
    expect(screen.getByTestId("run-status")).toHaveTextContent("Cancelled");
    expect(requestBadge()).toHaveTextContent("Cancelled");
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
    expect(requestBadge()).toHaveTextContent("Failed");
    expect(await within(latest()).findByText(/failed: run_command is closed this sprint/)).toBeInTheDocument();
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

  it("shows the failure notice for a failed project opened without a request in this session", async () => {
    const api = new MockAgentApi(0);
    await api.createProject("Old");
    await api.sendChat(1, "Create a blog (simulate failure)");
    window.localStorage.setItem(PROJECT_STORAGE_KEY, "1");

    render(<App api={api} />);

    expect(await screen.findByText(/The last run stopped after a failure/)).toBeInTheDocument();
    expect(screen.queryByTestId("request-status")).not.toBeInTheDocument();
    // The failed task carries the backend's reason, read from GET /logs.
    expect(
      await within(region("Agent status")).findByText(/Mock failure: about\.html was not written/),
    ).toBeInTheDocument();
  });
});
