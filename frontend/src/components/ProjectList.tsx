import type { Project } from "../services/types";
import { formatDate } from "../utils/format";

interface Props {
  projects: Project[];
  loading: boolean;
  onOpen: (project: Project) => void;
}

/** Existing projects on the start screen, newest first, so the user can reopen one. */
export function ProjectList({ projects, loading, onOpen }: Props) {
  return (
    <section className="card project-list" aria-label="Existing projects">
      <h2>Open a project</h2>
      {loading ? (
        <p className="muted">Loading projects…</p>
      ) : projects.length === 0 ? (
        <p className="muted">No projects yet.</p>
      ) : (
        <ul>
          {[...projects].reverse().map((p) => (
            <li key={p.id}>
              <button type="button" className="link" onClick={() => onOpen(p)}>
                {p.name}
              </button>
              <span className="muted">{formatDate(p.created_at)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
