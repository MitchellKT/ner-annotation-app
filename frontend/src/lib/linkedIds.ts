// An entity's `uid` may link it to several external ids, stored as a single
// comma-separated string (e.g. "Q328,Q42"). These helpers are the one place
// that knows that format: parsing, normalizing on save, and picking the id
// that is shown (always the first one).

/** Split a stored/typed uid into its ids: trimmed, blanks dropped, de-duplicated (order kept). */
export function parseLinkedIds(uid: string | undefined | null): string[] {
  if (!uid) return [];
  const out: string[] = [];
  for (const part of uid.split(",")) {
    const id = part.trim();
    if (id && !out.includes(id)) out.push(id);
  }
  return out;
}

/** Canonical stored form ("a,b,c"), or undefined when there are no ids. */
export function normalizeLinkedIds(raw: string | undefined | null): string | undefined {
  const ids = parseLinkedIds(raw);
  return ids.length ? ids.join(",") : undefined;
}

/** The id that is displayed / looked up: the first one. */
export function primaryLinkedId(uid: string | undefined | null): string | undefined {
  return parseLinkedIds(uid)[0];
}

/** Editable form shown in the id prompt ("a, b, c"). */
export function formatLinkedIds(uid: string | undefined | null): string {
  return parseLinkedIds(uid).join(", ");
}
