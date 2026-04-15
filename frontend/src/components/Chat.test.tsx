/** Chat component tests — focus on the UI contract, not the chat logic. */
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ChatMessage } from "../api/client";
import { Chat } from "./Chat";

const baseProps = {
  status: "shaping" as const,
  messages: [] as ChatMessage[],
  sending: false,
  onSend: () => {},
  phaseLabel: "Shaping",
  readyToLaunch: false,
};

describe("Chat", () => {
  it("renders the empty-state hint in shaping status", () => {
    render(<Chat {...baseProps} />);
    expect(screen.getByText(/describing your project idea/i)).toBeInTheDocument();
  });

  it("renders user and lead bubbles with the right speaker labels", () => {
    const messages: ChatMessage[] = [
      { id: 1, role: "user", content: "hello there", created_at: "2026-01-01" },
      { id: 2, role: "lead", content: "hi back", created_at: "2026-01-01" },
    ];
    render(<Chat {...baseProps} messages={messages} />);
    // "You" appears once — only as the user bubble's speaker label.
    expect(screen.getByText("You")).toBeInTheDocument();
    // "Lead" shows twice (header + bubble speaker) — scope to the bubble area.
    const leadSpeakers = screen.getAllByText("Lead");
    expect(leadSpeakers.length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("hello there")).toBeInTheDocument();
    expect(screen.getByText("hi back")).toBeInTheDocument();
  });

  it("shows the Launch CTA only when readyToLaunch is true", () => {
    const { rerender } = render(
      <Chat {...baseProps} readyToLaunch={false} onLaunch={() => {}} />,
    );
    expect(screen.queryByText(/Brief is ready/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Launch Stage 1/ })).toBeNull();

    rerender(<Chat {...baseProps} readyToLaunch={true} onLaunch={() => {}} />);
    expect(screen.getByText(/Brief is ready/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Launch Stage 1/ })).toBeInTheDocument();
  });

  it("fires onLaunch when the CTA is clicked", () => {
    const onLaunch = vi.fn();
    render(<Chat {...baseProps} readyToLaunch={true} onLaunch={onLaunch} />);
    fireEvent.click(screen.getByRole("button", { name: /Launch Stage 1/ }));
    expect(onLaunch).toHaveBeenCalledOnce();
  });

  it("sends the draft on Enter and clears the textarea", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<Chat {...baseProps} onSend={onSend} />);
    const textarea = screen.getByRole("textbox");
    await user.type(textarea, "hello world");
    await user.keyboard("{Enter}");
    expect(onSend).toHaveBeenCalledWith("hello world");
    expect((textarea as HTMLTextAreaElement).value).toBe("");
  });

  it("uses Shift+Enter to insert a newline (does not send)", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<Chat {...baseProps} onSend={onSend} />);
    const textarea = screen.getByRole("textbox");
    await user.type(textarea, "line1");
    await user.keyboard("{Shift>}{Enter}{/Shift}");
    await user.type(textarea, "line2");
    expect(onSend).not.toHaveBeenCalled();
    expect((textarea as HTMLTextAreaElement).value).toContain("line1");
    expect((textarea as HTMLTextAreaElement).value).toContain("line2");
  });

  it("disables the send button when sending or draft is empty", async () => {
    const user = userEvent.setup();
    const { rerender } = render(<Chat {...baseProps} />);
    const button = screen.getByRole("button", { name: /send/i });
    expect(button).toBeDisabled();

    const textarea = screen.getByRole("textbox");
    await user.type(textarea, "x");
    expect(button).not.toBeDisabled();

    rerender(<Chat {...baseProps} sending />);
    expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
  });
});
