import { describe, it, expect } from "vitest";
import { toCodePoints, cpSlice, normalizeSelection } from "./offsets";

describe("code-point helpers", () => {
  it("counts astral chars as single code points", () => {
    const cps = toCodePoints("😀 Bob");
    expect(cps.length).toBe(5); // 😀, space, B, o, b
    expect(cpSlice(cps, 2, 5)).toBe("Bob");
  });
});

describe("normalizeSelection", () => {
  const cps = toCodePoints("Alice met Bob.");

  it("returns null for whitespace-only selection", () => {
    expect(normalizeSelection(cps, 5, 6, true)).toBeNull(); // the space between words
  });

  it("trims surrounding whitespace", () => {
    // " met " region around indices 5..10 -> trims to "met"
    expect(normalizeSelection(cps, 5, 10, false)).toEqual({ start: 6, end: 9 });
  });

  it("snaps a partial word out to whole-word boundaries", () => {
    // "lic" inside Alice (1..4) -> "Alice" (0..5)
    expect(normalizeSelection(cps, 1, 4, true)).toEqual({ start: 0, end: 5 });
  });

  it("does not grow across whitespace when snapping", () => {
    // exactly "Alice" (0..5) stays put, does not eat the following space/word
    expect(normalizeSelection(cps, 0, 5, true)).toEqual({ start: 0, end: 5 });
  });

  it("orders reversed selections", () => {
    expect(normalizeSelection(cps, 9, 6, false)).toEqual({ start: 6, end: 9 });
  });
});
