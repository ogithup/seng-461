import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import App from "../App";
import { ApiError } from "../services/errors";
import { MockAgentApi } from "../services/mockApi";

async function startProject(name = "Blog") {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Project name"), name);
  await user.click(screen.getByRole("button", { name: "Create project" }));
  await screen.findByText(/Project:/);
  return user;
}

describe("App — Sprint 1 UI", () => {
  it("shows chat input, send button and status panel after creating a project", async () => {
    render(<App api={new MockAgentApi(0)} />);
    await startProject();

    expect(screen.getByLabelText("Message to the agent")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(screen.getByTestId("run-status")).toHaveTextContent("Idle");
    expect(screen.getByText("No tasks yet.")).toBeInTheDocument();
  });

  it("sends “Create a blog” and displays the returned tasks", async () => {
    render(<App api={new MockAgentApi(0)} />);
    const user = await startProject();

    await user.type(screen.getByLabelText("Message to the agent"), "Create a blog");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("Finished 2 task(s).")).toBeInTheDocument();
    const status = screen.getByRole("region", { name: "Agent status" });
    expect(within(status).getByTestId("run-status")).toHaveTextContent("Completed");
    expect(within(status).getByText("create project")).toBeInTheDocument();
    expect(within(status).getByText("create index.html")).toBeInTheDocument();
    expect(within(status).getByText("2/2 tasks done")).toBeInTheDocument();
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

  it("shows an error banner when the backend is unreachable", async () => {
    const api = new MockAgentApi(0);
    vi.spyOn(api, "createProject").mockRejectedValue(
      new ApiError(0, { code: "network_error", message: "Network error" }),
    );
    render(<App api={api} />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Project name"), "Blog");
    await user.click(screen.getByRole("button", { name: "Create project" }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/Can't reach the backend/));
  });
});
