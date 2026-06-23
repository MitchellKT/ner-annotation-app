// Offsets are **code-point** indices (matching Python `str` / `len`), but JS
// strings are UTF-16. These helpers keep the two consistent and turn a raw DOM
// selection into a clean (start, end) span.

/** Code-point array for a string (one entry per Unicode scalar). */
export function toCodePoints(text: string): string[] {
  return Array.from(text);
}

/** Slice by code-point offsets (NOT String.prototype.slice, which is UTF-16). */
export function cpSlice(cps: string[], start: number, end: number): string {
  return cps.slice(start, end).join("");
}

const WORD_RE = /[\p{L}\p{N}_]/u;
const SPACE_RE = /\s/u;

function isWord(cp: string | undefined): boolean {
  return cp !== undefined && WORD_RE.test(cp);
}
function isSpace(cp: string | undefined): boolean {
  return cp !== undefined && SPACE_RE.test(cp);
}

export interface Span {
  start: number;
  end: number;
}

/**
 * Clean up a raw selection: clamp, order, trim surrounding whitespace, and
 * (optionally) snap boundaries outward to whole-word edges. Snapping only grows
 * across a boundary that sits *inside* a word — it never swallows whitespace.
 * Returns null for an empty/whitespace-only selection.
 */
export function normalizeSelection(
  cps: string[],
  rawStart: number,
  rawEnd: number,
  snap: boolean
): Span | null {
  const n = cps.length;
  let start = clamp(Math.min(rawStart, rawEnd), 0, n);
  let end = clamp(Math.max(rawStart, rawEnd), 0, n);

  while (start < end && isSpace(cps[start])) start++;
  while (end > start && isSpace(cps[end - 1])) end--;
  if (start >= end) return null;

  if (snap) {
    while (start > 0 && isWord(cps[start - 1]) && isWord(cps[start])) start--;
    while (end < n && isWord(cps[end]) && isWord(cps[end - 1])) end++;
  }
  return { start, end };
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(v, hi));
}

// ---------------------------------------------------------------- DOM mapping
// The text panel renders each segment as <span data-start="<cpStart>">…</span>.
// Convert a DOM (node, utf16offset) position to a global code-point offset by
// walking up to the owning segment and counting code points in the prefix.

function cpOffsetFromDom(node: Node, utf16Offset: number): number | null {
  let el: HTMLElement | null =
    node.nodeType === Node.TEXT_NODE ? node.parentElement : (node as HTMLElement);
  const seg = el?.closest<HTMLElement>("[data-start]");
  if (!seg || seg.dataset.start === undefined) return null;
  const segStart = Number(seg.dataset.start);

  if (node.nodeType === Node.TEXT_NODE) {
    const prefix = (node.textContent ?? "").slice(0, utf16Offset);
    return segStart + Array.from(prefix).length;
  }
  // Selection landed on the element boundary: offset counts child nodes.
  const childTextBefore = Array.from(node.childNodes)
    .slice(0, utf16Offset)
    .map((c) => c.textContent ?? "")
    .join("");
  return segStart + Array.from(childTextBefore).length;
}

/** Map the current window selection (inside `root`) to a code-point span. */
export function selectionToSpan(root: HTMLElement): Span | null {
  const sel = window.getSelection();
  if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return null;
  const range = sel.getRangeAt(0);
  if (!root.contains(range.startContainer) || !root.contains(range.endContainer)) return null;

  const a = cpOffsetFromDom(range.startContainer, range.startOffset);
  const b = cpOffsetFromDom(range.endContainer, range.endOffset);
  if (a === null || b === null) return null;
  return { start: Math.min(a, b), end: Math.max(a, b) };
}
