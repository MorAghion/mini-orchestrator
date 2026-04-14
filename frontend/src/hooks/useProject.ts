import { useCallback, useEffect, useState } from "react";
import { api, ProjectDetail } from "../api/client";

/** Fetches project detail, re-fetching on a timer or when `tick` changes. */
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

  useEffect(() => {
    refetch();
  }, [refetch, tick]);

  return { data, error, refetch };
}
