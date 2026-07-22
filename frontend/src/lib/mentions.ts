// Fragment helpers for (possibly non-continuous) mentions. A mention is one or
// more non-overlapping code-point spans ("fragments"); a continuous mention is
// simply the single-fragment case.

import type { Span } from "./offsets";
import type { WireMention, WireSpan } from "../types";

/** Sort fragments and coalesce overlapping/adjacent ones. */
export function mergeFragments(fragments: Span[]): Span[] {
  if (fragments.length === 0) return [];
  const ordered = [...fragments].sort((a, b) => a.start - b.start || a.end - b.end);
  const merged: Span[] = [{ ...ordered[0] }];
  for (let i = 1; i < ordered.length; i++) {
    const f = ordered[i];
    const last = merged[merged.length - 1];
    if (f.start <= last.end) last.end = Math.max(last.end, f.end);
    else merged.push({ ...f });
  }
  return merged;
}

/** Canonical string key for a fragment list, e.g. "0:5+17:27". */
export function fragmentsKey(fragments: WireSpan[]): string {
  return fragments.map((f) => `${f.start}:${f.end}`).join("+");
}

/** Normalize a wire mention (legacy {start,end} or {fragments}) to fragments. */
export function wireFragments(m: WireMention): WireSpan[] {
  if ("fragments" in m) return m.fragments;
  return [{ start: m.start, end: m.end }];
}

/** Whether a wire mention is flagged relative (absent flag = not relative). */
export function wireRelative(m: WireMention): boolean {
  return Boolean((m as { relative?: boolean }).relative);
}

/**
 * Serialize fragments back to the wire: single-fragment stays {start,end}. The
 * `relative` flag is only emitted when true, so ordinary mentions keep the
 * original on-disk shape.
 */
export function toWireMention(fragments: Span[], relative = false): WireMention {
  const rel = relative ? { relative: true as const } : {};
  if (fragments.length === 1)
    return { start: fragments[0].start, end: fragments[0].end, ...rel };
  return { fragments: fragments.map((f) => ({ start: f.start, end: f.end })), ...rel };
}
