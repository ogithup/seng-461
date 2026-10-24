import { FormEvent, useState } from "react";
import { MAX_PROJECT_NAME_LENGTH } from "../services/types";

interface Props {
  onCreate: (name: string) => void;
  busy: boolean;
}

export function ProjectForm({ onCreate, busy }: Props) {
  const [name, setName] = useState("");
  const trimmed = name.trim();

  function submit(e: FormEvent) {
    e.preventDefault();
    if (trimmed && !busy) onCreate(trimmed);
  }

  return (
    <form className="card project-form" onSubmit={submit}>
      <h2>Start a project</h2>
      <p className="muted">Name your project, then describe what the agent should build.</p>
      <label htmlFor="project-name">Project name</label>
      <div className="row">
        <input
          id="project-name"
          value={name}
          maxLength={MAX_PROJECT_NAME_LENGTH}
          placeholder="e.g. My blog"
          onChange={(e) => setName(e.target.value)}
          disabled={busy}
          autoFocus
        />
        <button type="submit" disabled={!trimmed || busy}>
          {busy ? "Creating…" : "Create project"}
        </button>
      </div>
    </form>
  );
}
