import { useCallback, useEffect, useState } from "react";
import { api, Note } from "../api/client";

export function useNotes(projectId: string | null, tick: number = 0) {
  const [notes, setNotes] = useState<Note[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!projectId) return;
    try {
      const list = await api.getNotes(projectId);
      setNotes(list);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [projectId]);

  useEffect(() => {
    refresh();
  }, [refresh, tick]);

  const drop = useCallback(
    async (noteId: string) => {
      if (!projectId) return;
      await api.deleteNote(projectId, noteId);
      await refresh();
    },
    [projectId, refresh],
  );

  return { notes, error, refresh, drop };
}
