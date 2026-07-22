import { describe, expect, it } from "vitest";
import { fragmentsKey, mergeFragments, toWireMention, wireFragments, wireRelative } from "./mentions";

describe("mergeFragments", () => {
  it("sorts fragments by start", () => {
    expect(mergeFragments([{ start: 17, end: 27 }, { start: 0, end: 5 }])).toEqual([
      { start: 0, end: 5 },
      { start: 17, end: 27 },
    ]);
  });

  it("coalesces overlapping fragments", () => {
    expect(mergeFragments([{ start: 0, end: 4 }, { start: 3, end: 8 }])).toEqual([
      { start: 0, end: 8 },
    ]);
  });

  it("coalesces adjacent fragments into a continuous span", () => {
    expect(mergeFragments([{ start: 0, end: 4 }, { start: 4, end: 8 }])).toEqual([
      { start: 0, end: 8 },
    ]);
  });

  it("keeps genuinely disjoint fragments separate", () => {
    expect(
      mergeFragments([{ start: 10, end: 12 }, { start: 0, end: 5 }, { start: 7, end: 9 }])
    ).toEqual([
      { start: 0, end: 5 },
      { start: 7, end: 9 },
      { start: 10, end: 12 },
    ]);
  });

  it("does not mutate its input", () => {
    const input = [{ start: 5, end: 7 }, { start: 0, end: 2 }];
    mergeFragments(input);
    expect(input[0]).toEqual({ start: 5, end: 7 });
  });
});

describe("wire round-trip", () => {
  it("reads legacy {start,end} mentions as one fragment", () => {
    expect(wireFragments({ start: 3, end: 9 })).toEqual([{ start: 3, end: 9 }]);
  });

  it("reads the fragments form as-is", () => {
    const frags = [{ start: 0, end: 5 }, { start: 17, end: 27 }];
    expect(wireFragments({ fragments: frags })).toEqual(frags);
  });

  it("writes single-fragment mentions in the legacy shape", () => {
    expect(toWireMention([{ start: 3, end: 9 }])).toEqual({ start: 3, end: 9 });
  });

  it("writes multi-fragment mentions in the fragments shape", () => {
    expect(toWireMention([{ start: 0, end: 5 }, { start: 17, end: 27 }])).toEqual({
      fragments: [{ start: 0, end: 5 }, { start: 17, end: 27 }],
    });
  });

  it("omits the relative flag when the mention is not relative", () => {
    expect(toWireMention([{ start: 3, end: 9 }], false)).toEqual({ start: 3, end: 9 });
    expect(toWireMention([{ start: 3, end: 9 }])).not.toHaveProperty("relative");
  });

  it("writes the relative flag on continuous and non-continuous mentions", () => {
    expect(toWireMention([{ start: 3, end: 9 }], true)).toEqual({
      start: 3,
      end: 9,
      relative: true,
    });
    expect(toWireMention([{ start: 0, end: 5 }, { start: 17, end: 27 }], true)).toEqual({
      fragments: [{ start: 0, end: 5 }, { start: 17, end: 27 }],
      relative: true,
    });
  });

  it("reads the relative flag from either wire form (absent = not relative)", () => {
    expect(wireRelative({ start: 3, end: 9 })).toBe(false);
    expect(wireRelative({ start: 3, end: 9, relative: true })).toBe(true);
    expect(wireRelative({ fragments: [{ start: 0, end: 5 }], relative: true })).toBe(true);
  });
});

describe("fragmentsKey", () => {
  it("distinguishes a discontinuous mention from its parts", () => {
    const key = fragmentsKey([{ start: 0, end: 5 }, { start: 17, end: 27 }]);
    expect(key).toBe("0:5+17:27");
    expect(key).not.toBe(fragmentsKey([{ start: 0, end: 5 }]));
  });
});
