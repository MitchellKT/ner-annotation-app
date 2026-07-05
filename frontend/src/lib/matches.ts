// Find repeated occurrences of an annotated span's surface text, so a mention
// can be propagated to every identical match in the document (Ctrl+F style:
// plain substring scan, non-overlapping, but case-SENSITIVE since entity
// surface forms are case-carrying).

import type { Span } from "./offsets";

/**
 * All other occurrences of `cps[span.start..span.end)` in the document, as
 * spans. The original span itself is excluded; matches are found left-to-right
 * and don't overlap each other. Whitespace-only targets yield nothing.
 */
export function findOccurrences(cps: string[], span: Span): Span[] {
  const len = span.end - span.start;
  if (len <= 0 || span.start < 0 || span.end > cps.length) return [];
  const target = cps.slice(span.start, span.end);
  if (target.every((c) => /\s/u.test(c))) return [];

  const out: Span[] = [];
  let i = 0;
  while (i + len <= cps.length) {
    let match = true;
    for (let j = 0; j < len; j++) {
      if (cps[i + j] !== target[j]) {
        match = false;
        break;
      }
    }
    if (match) {
      if (i !== span.start) out.push({ start: i, end: i + len });
      i += len; // non-overlapping, like a find-next loop
    } else {
      i++;
    }
  }
  return out;
}
