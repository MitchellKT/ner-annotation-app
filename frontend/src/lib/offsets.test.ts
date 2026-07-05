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
    expect(normalizeSelection(cps, 5, 6)).toBeNull(); // the space between words
  });

  it("trims surrounding whitespace", () => {
    // " met " region around indices 5..10 -> trims to "met"
    expect(normalizeSelection(cps, 5, 10)).toEqual({ start: 6, end: 9 });
  });

  it("orders reversed selections", () => {
    expect(normalizeSelection(cps, 9, 6)).toEqual({ start: 6, end: 9 });
  });
});
