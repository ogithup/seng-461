// Display helpers shared by the panels. Timestamps from the API are ISO 8601 in UTC.

export function formatTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? iso
    : date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function formatDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? iso
    : date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  return `${(bytes / 1024).toFixed(1)} KB`;
}

export function formatDuration(ms: number): string {
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

// A task prompt may end in an opaque token the agent reads back later, e.g.
// `Write index.html (blog site "X") [delta:eJyr…]` (Sprint 4 orchestrator). It means nothing to
// a person, so it is hidden from the label; the full prompt stays available as a tooltip.
const MACHINE_SUFFIX = /\s+\[[a-z]+:[A-Za-z0-9_-]{8,}\]$/;

export function displayPrompt(prompt: string): string {
  return prompt.replace(MACHINE_SUFFIX, "");
}
