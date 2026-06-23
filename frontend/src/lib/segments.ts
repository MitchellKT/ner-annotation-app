// Tile the document text into maximal segments: contiguous code-point runs that
// share exactly the same set of covering mentions. This is what makes nested /
// overlapping spans renderable — each segment knows every entity covering it, so
// the renderer can paint one background plus stacked underline bars.

export interface SpanInput {
  entityId: string;
  mentionId: string;
  start: number;
  end: number;
}

export interface Segment {
  start: number;
  end: number;
  // Entities covering this run, in input order. Empty => plain (uncovered) text.
  entityIds: string[];
  mentionIds: string[];
}

/**
 * Produce a full, gap-free tiling of [0, textLen). Uncovered runs are returned
 * with empty `entityIds` so the caller can render them as plain text.
 */
export function computeSegments(textLen: number, spans: SpanInput[]): Segment[] {
  if (textLen <= 0) return [];

  const boundaries = new Set<number>([0, textLen]);
  for (const s of spans) {
    const a = clamp(s.start, 0, textLen);
    const b = clamp(s.end, 0, textLen);
    if (b > a) {
      boundaries.add(a);
      boundaries.add(b);
    }
  }
  const points = [...boundaries].sort((x, y) => x - y);

  const segments: Segment[] = [];
  for (let i = 0; i < points.length - 1; i++) {
    const start = points[i];
    const end = points[i + 1];
    if (end <= start) continue;
    const entityIds: string[] = [];
    const mentionIds: string[] = [];
    const seenEntities = new Set<string>();
    for (const s of spans) {
      if (s.start <= start && s.end >= end) {
        mentionIds.push(s.mentionId);
        if (!seenEntities.has(s.entityId)) {
          seenEntities.add(s.entityId);
          entityIds.push(s.entityId);
        }
      }
    }
    segments.push({ start, end, entityIds, mentionIds });
  }
  return segments;
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(v, hi));
}
