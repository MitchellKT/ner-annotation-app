import { describe, expect, it } from "vitest";
import { formatLinkedIds, normalizeLinkedIds, parseLinkedIds, primaryLinkedId } from "./linkedIds";

describe("linked ids", () => {
  it("parses a single id", () => {
    expect(parseLinkedIds("Q76")).toEqual(["Q76"]);
    expect(primaryLinkedId("Q76")).toBe("Q76");
  });

  it("splits, trims, drops blanks and duplicates, keeping order", () => {
    expect(parseLinkedIds(" Q2 , Q1,,Q2 , ")).toEqual(["Q2", "Q1"]);
    expect(primaryLinkedId(" Q2 , Q1")).toBe("Q2");
  });

  it("handles empty input", () => {
    expect(parseLinkedIds(undefined)).toEqual([]);
    expect(parseLinkedIds(" , ")).toEqual([]);
    expect(normalizeLinkedIds(" , ")).toBeUndefined();
    expect(primaryLinkedId("")).toBeUndefined();
  });

  it("normalizes to the comma-separated stored form", () => {
    expect(normalizeLinkedIds("Q1, Q2 ,Q3")).toBe("Q1,Q2,Q3");
    expect(formatLinkedIds("Q1,Q2")).toBe("Q1, Q2");
  });

  it("keeps non-latin ids verbatim", () => {
    expect(parseLinkedIds("ישות-1, ישות-2")).toEqual(["ישות-1", "ישות-2"]);
  });
});
