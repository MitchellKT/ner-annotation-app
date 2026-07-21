import { useEffect, useRef, useState } from "react";
import { useStore } from "../store";
import type { Comment } from "../types";

/**
 * Document-level comments, shown under the entity list.
 *
 * The thread is *shared*: every annotator reads and writes the same notes, so
 * each one is headed by its author's username and the time it was written, and
 * the panel refetches whenever it is opened. Collapsed by default so it never
 * competes with the entity list for space — the header keeps showing the count.
 */
function formatWhen(iso: string): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return iso;
  return at.toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
}

// Author + timestamp + body identify a comment; the backend dedupes on the same
// triple, so it is also a stable React key.
const keyOf = (c: Comment) => `${c.created_at}|${c.author}|${c.text}`;

export function CommentPanel() {
  const comments = useStore((s) => s.comments);
  const open = useStore((s) => s.commentsOpen);
  const docId = useStore((s) => s.docId);
  const username = useStore((s) => s.username);
  const setCommentsOpen = useStore((s) => s.setCommentsOpen);
  const postComment = useStore((s) => s.postComment);

  const [draft, setDraft] = useState("");
  const [posting, setPosting] = useState(false);
  const boxRef = useRef<HTMLTextAreaElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Opening the panel (button or `c`) puts the cursor straight in the box —
  // but only on that transition: the panel stays open across documents, and
  // grabbing focus there would swallow the annotation shortcuts.
  const wasOpen = useRef(open);
  useEffect(() => {
    if (open && !wasOpen.current) boxRef.current?.focus();
    wasOpen.current = open;
  }, [open]);

  // Keep the newest comment in view as the thread grows.
  useEffect(() => {
    if (open && listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [open, comments]);

  if (!docId) return null;

  async function post() {
    const text = draft.trim();
    if (!text || posting) return;
    setPosting(true);
    try {
      await postComment(text);
      setDraft("");
    } finally {
      setPosting(false);
      boxRef.current?.focus();
    }
  }

  function onKeyDown(e: React.KeyboardEvent) {
    // Enter alone inserts a newline — comments are often more than one line.
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      void post();
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      setCommentsOpen(false);
    }
  }

  return (
    <div className={"comment-panel" + (open ? " open" : "")}>
      <button
        className="comment-head"
        onClick={() => setCommentsOpen(!open)}
        title="document comments, shared with every annotator (c)"
      >
        <span className="comment-caret">{open ? "▾" : "▸"}</span>
        <span>💬 Comments</span>
        {comments.length > 0 && <span className="comment-count">{comments.length}</span>}
      </button>

      {open && (
        <>
          <div className="comment-list" ref={listRef}>
            {comments.length === 0 && (
              <div className="comment-empty">
                No comments yet — notes here are shared with every annotator.
              </div>
            )}
            {comments.map((c) => (
              <div
                key={keyOf(c)}
                className={"comment" + (c.author === username ? " mine" : "")}
              >
                <div className="comment-meta">
                  <span className="comment-author">
                    <bdi>{c.author}</bdi>
                  </span>
                  <span className="comment-time" title={c.created_at}>
                    {formatWhen(c.created_at)}
                  </span>
                </div>
                <div className="comment-body">
                  <bdi>{c.text}</bdi>
                </div>
              </div>
            ))}
          </div>

          <div className="comment-compose">
            <textarea
              ref={boxRef}
              className="comment-input"
              rows={2}
              value={draft}
              placeholder={`Comment as ${username ?? "…"} — Ctrl+Enter to post`}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKeyDown}
            />
            <button
              className="primary"
              disabled={!draft.trim() || posting}
              onClick={() => void post()}
              title="post the comment (Ctrl+Enter)"
            >
              {posting ? "Posting…" : "Post"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
