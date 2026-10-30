import type { PreviewState } from "../hooks/usePreview";

interface Props {
  preview: PreviewState;
  /** The agent is still working, so the site may be incomplete. */
  busy: boolean;
  onReload: () => void;
}

/**
 * The generated site. It is untrusted code: the frame only gets `allow-scripts` (no same
 * origin), and the API also serves it with `Content-Security-Policy: sandbox allow-scripts`.
 */
export function PreviewPanel({ preview, busy, onReload }: Props) {
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
              No preview yet. Ask the agent to build a site; it appears here once it has an
              index.html.
            </p>
          )}
        </div>
      )}
    </section>
  );
}
