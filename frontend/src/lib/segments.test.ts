import { describe, it, expect } from "vitest";
import { computeSegments } from "./segments";

describe("computeSegments", () => {
  it("tiles plain text as a single uncovered segment", () => {
    expect(computeSegments(5, [])).toEqual([{ start: 0, end: 5, entityIds: [], mentionIds: [] }]);
  });

  it("produces gaps between disjoint spans", () => {
    // "Alice met Bob" -> [0,5)=Alice, [10,13)=Bob
    const segs = computeSegments(13, [
      { entityId: "e1", mentionId: "m1", start: 0, end: 5 },
      { entityId: "e2", mentionId: "m2", start: 10, end: 13 },
    ]);
    expect(segs).toEqual([
      { start: 0, end: 5, entityIds: ["e1"], mentionIds: ["m1"] },
      { start: 5, end: 10, entityIds: [], mentionIds: [] },
      { start: 10, end: 13, entityIds: ["e2"], mentionIds: ["m2"] },
    ]);
  });

  it("handles nested spans: inner segment carries both entities", () => {
    // "Bank of America": ORG [0,15), LOC [8,15)
    const segs = computeSegments(15, [
      { entityId: "org", mentionId: "mo", start: 0, end: 15 },
      { entityId: "loc", mentionId: "ml", start: 8, end: 15 },
    ]);
    expect(segs).toEqual([
      { start: 0, end: 8, entityIds: ["org"], mentionIds: ["mo"] },
      { start: 8, end: 15, entityIds: ["org", "loc"], mentionIds: ["mo", "ml"] },
    ]);
  });

  it("handles partial overlap of two spans", () => {
    const segs = computeSegments(10, [
      { entityId: "a", mentionId: "ma", start: 0, end: 6 },
      { entityId: "b", mentionId: "mb", start: 4, end: 10 },
    ]);
    expect(segs.map((s) => [s.start, s.end, s.entityIds])).toEqual([
      [0, 4, ["a"]],
      [4, 6, ["a", "b"]],
      [6, 10, ["b"]],
    ]);
  });

  it("clamps out-of-range spans and dedupes entity ids within a segment", () => {
    const segs = computeSegments(5, [
      { entityId: "e1", mentionId: "m1", start: -3, end: 99 },
      { entityId: "e1", mentionId: "m2", start: 0, end: 5 },
    ]);
    expect(segs).toEqual([{ start: 0, end: 5, entityIds: ["e1"], mentionIds: ["m1", "m2"] }]);
  });
});
