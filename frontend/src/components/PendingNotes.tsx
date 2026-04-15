import { Note } from "../api/client";

interface Props {
  notes: Note[];
  onDrop: (noteId: string) => void;
}

export function PendingNotes({ notes, onDrop }: Props) {
  return (
    <div className="pending-notes">
      <div className="pending-notes-header">
        <h4>Pending notes</h4>
        <span className="pending-notes-count">{notes.length}</span>
      </div>
      {notes.length === 0 ? (
        <div className="pending-notes-empty">
          Drop a note in chat (e.g.{" "}
          <em>&ldquo;oh, also support emoji reactions&rdquo;</em>) and it
          lands here. The Reviewer absorbs pending notes when it next runs.
        </div>
      ) : (
        <>
          <div className="pending-notes-chips">
            {notes.map((n) => (
              <div key={n.id} className="note-chip" title={n.content}>
                <span className="note-content">{n.content}</span>
                <button
                  className="note-drop"
                  onClick={() => onDrop(n.id)}
                  aria-label="drop note"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
          <div className="pending-notes-caption">
            Queued for the Reviewer to absorb at review time.
          </div>
        </>
      )}
    </div>
  );
}
