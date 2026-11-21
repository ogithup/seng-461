import type { PendingAction } from "../services/types";
import { formatTime } from "../utils/format";

interface Props {
  action: PendingAction;
  busy: boolean;
  onApprove: () => void;
  onReject: () => void;
}

/**
 * Shows the exact command the server is holding for a human decision. The server decides what
 * needs approval and what a decision does; this card only reports the human's choice.
 */
export function ApprovalCard({ action, busy, onApprove, onReject }: Props) {
  return (
    <div className="approval" role="group" aria-label="Approval required" aria-busy={busy}>
      <p className="approval-title">The agent wants to run this command:</p>
      <pre className="approval-command">
        <code>{action.command}</code>
      </pre>
      {action.reason && <p className="approval-meta">Reason: {action.reason}</p>}
      <p className="approval-meta">Expires at {formatTime(action.expires_at)}</p>
      <div className="row">
        <button type="button" onClick={onApprove} disabled={busy}>
          Approve
        </button>
        <button type="button" className="danger" onClick={onReject} disabled={busy}>
          Reject
        </button>
      </div>
    </div>
  );
}
