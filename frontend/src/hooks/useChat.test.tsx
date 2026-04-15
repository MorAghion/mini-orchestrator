/** useChat hook: optimistic append + refresh on success, rollback on error. */
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { api as apiType } from "../api/client";
import { useChat } from "./useChat";

// Mock the API module so the hook sees whatever we program.
vi.mock("../api/client", () => {
  return {
    api: {
      getChatHistory: vi.fn(),
      sendChat: vi.fn(),
    } as unknown as typeof apiType,
  };
});

import { api } from "../api/client";

const mockedGetHistory = api.getChatHistory as unknown as ReturnType<typeof vi.fn>;
const mockedSendChat = api.sendChat as unknown as ReturnType<typeof vi.fn>;

describe("useChat", () => {
  beforeEach(() => {
    mockedGetHistory.mockReset();
    mockedSendChat.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads history on mount", async () => {
    mockedGetHistory.mockResolvedValueOnce([
      { id: 1, role: "user", content: "hi", created_at: "2026-01-01" },
    ]);
    const { result } = renderHook(() => useChat("proj-x"));
    await waitFor(() => expect(result.current.messages).toHaveLength(1));
    expect(result.current.messages[0].content).toBe("hi");
    expect(mockedGetHistory).toHaveBeenCalledWith("proj-x");
  });

  it("optimistically appends the user message and then refreshes from server", async () => {
    mockedGetHistory.mockResolvedValueOnce([]); // initial empty
    const { result } = renderHook(() => useChat("proj-x"));
    await waitFor(() => expect(result.current.messages).toEqual([]));

    // After send: server history should return both messages.
    mockedSendChat.mockResolvedValueOnce({
      user_message_id: 10,
      lead_message_id: 11,
      display_text: "hi back",
      brief_ready: false,
      note_queued: null,
      revision_request: null,
      cost_usd: 0.01,
    });
    mockedGetHistory.mockResolvedValueOnce([
      { id: 10, role: "user", content: "hello", created_at: "2026-01-01T00:00:00" },
      { id: 11, role: "lead", content: "hi back", created_at: "2026-01-01T00:00:01" },
    ]);

    let returnedReply: unknown;
    await act(async () => {
      returnedReply = await result.current.send("hello");
    });

    expect(returnedReply).toMatchObject({ display_text: "hi back", brief_ready: false });
    expect(result.current.messages).toHaveLength(2);
    expect(result.current.messages.map((m) => m.role)).toEqual(["user", "lead"]);
    expect(result.current.messages.map((m) => m.content)).toEqual(["hello", "hi back"]);
  });

  it("rolls back the optimistic append on send failure", async () => {
    mockedGetHistory.mockResolvedValueOnce([]);
    const { result } = renderHook(() => useChat("proj-x"));
    await waitFor(() => expect(result.current.messages).toEqual([]));

    mockedSendChat.mockRejectedValueOnce(new Error("network down"));

    await act(async () => {
      const r = await result.current.send("boom");
      expect(r).toBeNull();
    });

    expect(result.current.messages).toEqual([]); // rolled back
    expect(result.current.error).toMatch(/network down/);
    expect(result.current.sending).toBe(false);
  });

  it("no-ops when projectId is null", async () => {
    const { result } = renderHook(() => useChat(null));
    // No getChatHistory call should have fired
    expect(mockedGetHistory).not.toHaveBeenCalled();
    const r = await result.current.send("x");
    expect(r).toBeNull();
    expect(mockedSendChat).not.toHaveBeenCalled();
  });
});
