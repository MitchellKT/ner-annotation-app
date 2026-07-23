// Base text direction, used to lay out a mention's fragments the same way they
// read in the source document. A discontinuous mention's fragments are stored
// in logical (offset) order; in an RTL document the earliest fragment sits on
// the RIGHT, so the entity chip must render them right-to-left to match.

export type Dir = "ltr" | "rtl";

// Strongly right-to-left scripts (Hebrew, Arabic, Syriac, Thaana, N'Ko,
// Samaritan, Mandaic) via Script_Extensions, which the engine resolves for us.
const RTL_CHAR =
  /[\p{Script_Extensions=Hebrew}\p{Script_Extensions=Arabic}\p{Script_Extensions=Syriac}\p{Script_Extensions=Thaana}\p{Script_Extensions=Nko}\p{Script_Extensions=Samaritan}\p{Script_Extensions=Mandaic}]/u;
// Any letter counts as a strong directional character; a non-RTL letter is LTR.
const LETTER = /\p{L}/u;

/**
 * Base direction from the first strong directional character, matching the
 * Unicode bidi P2/P3 rules used by `dir="auto"`. Weak/neutral characters
 * (digits, punctuation, whitespace) are skipped; an all-neutral string is LTR.
 */
export function baseDirection(text: Iterable<string>): Dir {
  for (const ch of text) {
    if (RTL_CHAR.test(ch)) return "rtl";
    if (LETTER.test(ch)) return "ltr";
  }
  return "ltr";
}
