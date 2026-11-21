import type { PreviewState } from "../hooks/usePreview";

export interface PreviewNote {
  tone: "bad" | "muted";
  text: string;
}

interface Props {
  preview: PreviewState;
  /** The agent is still working, so the site may be incomplete. */
  busy: boolean;
  /** Something the user should know about what the preview shows (e.g. the last run failed). */
  note?: PreviewNote | null;
  /** Shown instead of the default when there is no preview (e.g. generation failed early). */
  emptyText?: string;
  /** Mock mode: the site was made in the browser, not by the backend. */
  mock: boolean;
  onReload: () => void;
}

/**
 * The generated site. It is untrusted code: the frame only gets `allow-scripts` (no same
 * origin), and the API also serves it with `Content-Security-Policy: sandbox allow-scripts`.
 */
export function PreviewPanel({ preview, busy, note, emptyText, mock, onReload }: Props) {
  const ready = preview.status === "ready";

  return (
    <section className="card preview-panel" aria-label="Preview">
      <div className="panel-head">
        <h2>Preview</h2>
        {ready && (
          <div className="panel-actions">
            {busy && <span className="muted">Updating…</span>}
            <button type="button" className="secondary small" onClick={onReload}>
              Reload
            </button>
            {/^https?:/.test(preview.url) && (
              <a href={preview.url} target="_blank" rel="noopener noreferrer">
                Open in new tab
              </a>
            )}
          </div>
        )}
      </div>
      {mock && <p className="mock-note">Mock mode: this site is made in the browser, not by the backend.</p>}
      {ready && note && <p className={note.tone === "bad" ? "panel-error" : "panel-note muted"}>{note.text}</p>}

      {ready ? (
        <iframe
          key={`${preview.url}#${preview.version}`}
          className="preview-frame"
          title="Website preview"
          src={preview.url}
          sandbox="allow-scripts"
          referrerPolicy="no-referrer"
        />
      ) : (
        <div className="preview-placeholder" data-testid="preview-state" data-state={preview.status}>
          {preview.status === "error" ? (
            <>
              <p className="panel-error">Couldn't load the preview: {preview.message}</p>
              <button type="button" className="secondary small" onClick={onReload}>
                Try again
              </button>
            </>
          ) : busy ? (
            <p className="muted">The agent is building the site…</p>
          ) : preview.status === "loading" ? (
            <p className="muted">Loading preview…</p>
          ) : (
            <p className="muted">
              {emptyText ??
                "No preview yet. Ask the agent to build a site; it appears here once it has an index.html."}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
