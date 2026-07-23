import { describe, expect, it } from "vitest";
import { baseDirection } from "./direction";

describe("baseDirection", () => {
  it("returns ltr for Latin text", () => {
    expect(baseDirection("Annie went to Washington")).toBe("ltr");
  });

  it("returns rtl for Hebrew text", () => {
    expect(baseDirection("שלום עולם")).toBe("rtl");
  });

  it("returns rtl for Arabic text", () => {
    expect(baseDirection("مرحبا بالعالم")).toBe("rtl");
  });

  it("uses the first strong character, ignoring leading neutrals", () => {
    // Leading punctuation/whitespace/quotes are neutral; the Hebrew word decides.
    expect(baseDirection('  «— שלום')).toBe("rtl");
  });

  it("skips weak characters like digits before the first strong letter", () => {
    expect(baseDirection("123 456 — مرحبا")).toBe("rtl");
  });

  it("detects an RTL document that embeds LTR names (the bug scenario)", () => {
    // The document is Hebrew but the mention surfaces (Annie, Washington) are
    // Latin — direction comes from the document, so its fragments read RTL.
    expect(baseDirection("אנני נסעה אל Washington")).toBe("rtl");
  });

  it("returns ltr for an all-neutral or empty string", () => {
    expect(baseDirection("  123 — !? ")).toBe("ltr");
    expect(baseDirection("")).toBe("ltr");
  });

  it("accepts a code-point array (as stored in the app)", () => {
    expect(baseDirection(Array.from("مرحبا"))).toBe("rtl");
  });
});
