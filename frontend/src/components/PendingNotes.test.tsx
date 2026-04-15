import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Note } from "../api/client";
import { PendingNotes } from "./PendingNotes";

function note(overrides: Partial<Note> = {}): Note {
  return {
    id: "note-1",
    content: "dark mode",
    source_msg_id: null,
    status: "pending",
    created_at: "2026-01-01",
    ...overrides,
  };
}

describe("PendingNotes", () => {
  it("renders nothing when the list is empty", () => {
    const { container } = render(<PendingNotes notes={[]} onDrop={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders one chip per note and shows the count", () => {
    render(
      <PendingNotes
        notes={[note({ id: "n1", content: "first" }), note({ id: "n2", content: "second" })]}
        onDrop={() => {}}
      />,
    );
    expect(screen.getByText("first")).toBeInTheDocument();
    expect(screen.getByText("second")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument(); // count badge
  });

  it("invokes onDrop with the note id when the ✕ is clicked", () => {
    const onDrop = vi.fn();
    render(<PendingNotes notes={[note({ id: "abc" })]} onDrop={onDrop} />);
    fireEvent.click(screen.getByRole("button", { name: /drop note/i }));
    expect(onDrop).toHaveBeenCalledWith("abc");
  });
});
