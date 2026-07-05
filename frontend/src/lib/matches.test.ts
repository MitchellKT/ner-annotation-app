import { describe, expect, it } from "vitest";
import { findOccurrences } from "./matches";
import { toCodePoints } from "./offsets";

const cps = (s: string) => toCodePoints(s);

describe("findOccurrences", () => {
  it("finds every other occurrence of the annotated text", () => {
    const text = "Alice met Bob, then Alice called Alice.";
    //            0123456789...   Alice @ 0, 20, 33
    expect(findOccurrences(cps(text), { start: 0, end: 5 })).toEqual([
      { start: 20, end: 25 },
      { start: 33, end: 38 },
    ]);
  });

  it("excludes the original span wherever it sits", () => {
    const text = "Alice met Alice";
    expect(findOccurrences(cps(text), { start: 10, end: 15 })).toEqual([{ start: 0, end: 5 }]);
  });

  it("is case-sensitive", () => {
    const text = "US buys us time";
    expect(findOccurrences(cps(text), { start: 0, end: 2 })).toEqual([]);
  });

  it("matches substrings like Ctrl+F (no word-boundary requirement)", () => {
    const text = "scan the scanner";
    expect(findOccurrences(cps(text), { start: 0, end: 4 })).toEqual([{ start: 9, end: 13 }]);
  });

  it("finds non-overlapping matches left to right", () => {
    const text = "aaaa";
    expect(findOccurrences(cps(text), { start: 0, end: 2 })).toEqual([{ start: 2, end: 4 }]);
  });

  it("uses code-point offsets for astral characters", () => {
    const text = "😀 Bob and 😀 Bob";
    // cps: 😀=0, ' '=1, B=2..4, ' '=5, a=6..8, ' '=9, 😀=10, ' '=11, B=12..14
    expect(findOccurrences(cps(text), { start: 2, end: 5 })).toEqual([{ start: 12, end: 15 }]);
  });

  it("ignores whitespace-only spans", () => {
    expect(findOccurrences(cps("a b c"), { start: 1, end: 2 })).toEqual([]);
  });
});
