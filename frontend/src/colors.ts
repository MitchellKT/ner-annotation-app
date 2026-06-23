// Per-entity color assignment. Entities get a stable, well-separated hue based on
// a counter so neighbouring entities are easy to tell apart. Each color exposes a
// light background tint (for the highlight fill) and a strong variant (underline /
// chip border / swatch).

export interface EntityColor {
  hue: number;
  bg: string; // light fill behind text
  bgActive: string; // slightly stronger fill for the active entity
  strong: string; // underline bar / swatch / border
  text: string; // readable text color on the strong swatch
}

// Golden-angle hue stepping → maximally distinct successive colors.
const GOLDEN_ANGLE = 137.508;

export function colorForIndex(i: number): EntityColor {
  const hue = Math.round((i * GOLDEN_ANGLE) % 360);
  return {
    hue,
    bg: `hsl(${hue} 70% 92%)`,
    bgActive: `hsl(${hue} 75% 85%)`,
    strong: `hsl(${hue} 65% 45%)`,
    text: `hsl(${hue} 65% 22%)`,
  };
}

// Canonical type accent colors (used on the type chip). Falls back to neutral.
const TYPE_COLORS: Record<string, string> = {
  PER: "#2563eb",
  LOC: "#16a34a",
  ORG: "#d97706",
  TIME: "#9333ea",
};

export function colorForType(type: string): string {
  return TYPE_COLORS[type] ?? "#64748b";
}
