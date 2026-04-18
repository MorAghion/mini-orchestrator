import { useEffect, useState } from "react";
import { OrchestratorEvent } from "../api/client";

export type { OrchestratorEvent };

/** Subscribes to the backend's per-project SSE stream. */
export function useEventStream(projectId: string | null) {
  const [events, setEvents] = useState<OrchestratorEvent[]>([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!projectId) return;
    // Reset when project changes
    setEvents([]);
    const source = new EventSource(`/api/projects/${projectId}/events`);
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);

    // The backend emits named events (e.g. event: task:started); register a
    // generic message handler to catch them. EventSource only delivers an event
    // to a named listener, not to onmessage. So we iterate known types.
    const EVENT_TYPES = [
      "project:created",
      "project:planned",
      "project:completed",
      "project:failed",
      "wave:started",
      "wave:completed",
      "task:started",
      "task:completed",
      "task:error",
      "task:retrying",
      "task:flagged",
      "artifact:created",
      "artifact:updated",
      "review:approved",
      "review:needs_rework",
    ];
    const handler = (e: MessageEvent) => {
      try {
        const parsed: OrchestratorEvent = JSON.parse(e.data);
        setEvents((prev) => [...prev, parsed]);
      } catch {
        // ignore non-JSON messages (e.g. pings)
      }
    };
    EVENT_TYPES.forEach((t) => source.addEventListener(t, handler));

    return () => {
      EVENT_TYPES.forEach((t) => source.removeEventListener(t, handler));
      source.close();
    };
  }, [projectId]);

  return { events, connected };
}
