import type { useProjectFiles } from "../hooks/useProjectFiles";
import { formatBytes } from "../utils/format";

interface Props {
  files: ReturnType<typeof useProjectFiles>;
}

/** The generated files in the project's workspace; click one to read it. */
export function FilesPanel({ files }: Props) {
  const { selected, content } = files;

  return (
    <section className="card files-panel" aria-label="Generated files">
      <h2>Files</h2>
      {files.error && <p className="panel-error">Couldn't list files: {files.error}</p>}
      {files.files.length === 0 ? (
        <p className="muted">{files.loading ? "Loading files…" : "No files generated yet."}</p>
      ) : (
        <ul className="file-list">
          {files.files.map((f) => (
            <li key={f.path}>
              <button
                type="button"
                className="file"
                aria-pressed={selected === f.path}
                onClick={() => files.open(selected === f.path ? null : f.path)}
              >
                <span className="file-path">{f.path}</span>
                <span className="muted">{formatBytes(f.size)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {files.truncated && <p className="muted">Only the first files are listed.</p>}

      {selected && (
        <div className="file-viewer">
          <div className="panel-head">
            <code>{selected}</code>
            <button type="button" className="secondary small" onClick={() => files.open(null)}>
              Close
            </button>
          </div>
          {files.contentError ? (
            <p className="panel-error">{files.contentError}</p>
          ) : content ? (
            <pre aria-label={`Contents of ${selected}`}>
              <code>{content.content}</code>
            </pre>
          ) : (
            <p className="muted">Loading…</p>
          )}
        </div>
      )}
    </section>
  );
}
