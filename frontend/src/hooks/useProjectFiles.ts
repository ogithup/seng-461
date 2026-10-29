import { useCallback, useEffect, useState } from "react";
import { describeError } from "../services/errors";
import type { AgentApi, FileContent, FileInfo } from "../services/types";

/**
 * Files in the project's workspace (GET /api/files) and the one the user is viewing
 * (GET /api/files/content). Both are refetched whenever `stamp` changes, since a new request
 * may have rewritten them.
 */
export function useProjectFiles(api: AgentApi, projectId: number | null, stamp: string) {
  const [files, setFiles] = useState<FileInfo[]>([]);
  const [truncated, setTruncated] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Tagged with its project, so switching projects never asks the new one for the old path.
  const [selection, setSelection] = useState<{ projectId: number; path: string } | null>(null);
  const selected = selection && selection.projectId === projectId ? selection.path : null;
  const [content, setContent] = useState<FileContent | null>(null);
  const [contentLoading, setContentLoading] = useState(false);
  const [contentError, setContentError] = useState<string | null>(null);

  useEffect(() => {
    setFiles([]);
    setTruncated(false);
    setError(null);
  }, [projectId]);

  useEffect(() => {
    if (projectId === null) return;
    let cancelled = false;
    setLoading(true);
    api.listFiles(projectId).then(
      (res) => {
        if (cancelled) return;
        setFiles(res.files);
        setTruncated(res.truncated);
        setError(null);
        setLoading(false);
      },
      (err) => {
        if (cancelled) return;
        setError(describeError(err));
        setLoading(false);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, projectId, stamp]);

  useEffect(() => {
    setContent(null);
    setContentError(null);
    if (projectId === null || selected === null) return;
    let cancelled = false;
    setContentLoading(true);
    api.getFileContent(projectId, selected).then(
      (res) => {
        if (cancelled) return;
        setContent(res);
        setContentLoading(false);
      },
      (err) => {
        if (cancelled) return;
        setContentError(describeError(err));
        setContentLoading(false);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, projectId, selected, stamp]);

  const open = useCallback(
    (path: string | null) => setSelection(path === null || projectId === null ? null : { projectId, path }),
    [projectId],
  );

  return {
    files,
    truncated,
    loading,
    error,
    selected,
    content,
    contentLoading,
    contentError,
    open,
  };
}
