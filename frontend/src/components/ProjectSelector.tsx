import type { Project } from "../services/types";

interface Props {
  projects: Project[];
  current: Project | null;
  onOpen: (project: Project) => void;
  onNew: () => void;
}

/** Top-bar switcher between existing projects, plus a way back to the start screen. */
export function ProjectSelector({ projects, current, onOpen, onNew }: Props) {
  return (
    <div className="project-selector">
      <label htmlFor="project-select">Project</label>
      <select
        id="project-select"
        value={current?.id ?? ""}
        onChange={(e) => {
          const next = projects.find((p) => p.id === Number(e.target.value));
          if (next && next.id !== current?.id) onOpen(next);
        }}
      >
        {!current && <option value="">Choose a project…</option>}
        {projects.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
      <button type="button" className="secondary" onClick={onNew}>
        New project
      </button>
    </div>
  );
}
