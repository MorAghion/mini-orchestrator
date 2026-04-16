import { useCallback, useEffect, useState } from "react";
import { api, ProjectDetail } from "../api/client";

const RUNNING_STATUSES = new Set(["planning", "stage1_running", "stage1_review"]);
const POLL_MS = 5000;

/** Fetches project detail, re-fetching on a timer or when `tick` changes.
 *
 * Polling fallback: when the project is in a running state, refetch every
 * POLL_MS milliseconds so the UI catches up even if an SSE completion event
 * was missed (e.g. tab came back from background, brief reconnect gap).
 */
export function useProject(projectId: string | null, tick: number = 0) {
  const [data, setData] = useState<ProjectDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    if (!projectId) return;
    try {
      const d = await api.getProject(projectId);
      setData(d);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [projectId]);

  // Clear stale data immediately when switching projects.
  useEffect(() => {
    setData(null);
    setError(null);
  }, [projectId]);

  // Fetch on mount + whenever a new SSE event arrives.
  useEffect(() => {
    refetch();
  }, [refetch, tick]);

  // Polling fallback while running — catches missed SSE completion events.
  const isRunning = RUNNING_STATUSES.has(data?.project.status ?? "");
  useEffect(() => {
    if (!projectId || !isRunning) return;
    const id = setInterval(refetch, POLL_MS);
    return () => clearInterval(id);
  }, [projectId, isRunning, refetch]);

  return { data, error, refetch };
}
