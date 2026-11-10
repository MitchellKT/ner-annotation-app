// External knowledge-base lookups for a linked entity id (the entity's `uid`).
//
// Everything that depends on the real knowledge base lives in this file:
// the attributes API, the optional image API, and the URL of the full entity
// page. The values below are PLACEHOLDERS — replace them with the real
// endpoints. Lookups are cached per id for the lifetime of the page.

/** One attribute as returned by the API: its Hebrew display name and Hebrew value. */
export interface EntityAttribute {
  name: string;
  value: string;
}

/**
 * The attributes API response: English attribute key → Hebrew name/value.
 * `title` is always present and is the entity's main name (the card title).
 */
export type EntityAttributes = { title: EntityAttribute } & Record<string, EntityAttribute>;

// ---- placeholders: replace with the real knowledge-base endpoints ----

/** Attributes API. `{id}` is replaced with the URL-encoded entity id. */
export const ENTITY_ATTRIBUTES_API = "/api/entities/{id}"; // PLACEHOLDER

/**
 * Optional image API, or null when there is none. Should respond with the image
 * itself, or JSON `{ "url": "..." }`; a 404 / empty response means "no image"
 * (not every entity type has one). `{id}` is replaced with the encoded id.
 */
export const ENTITY_IMAGE_API: string | null = null; // PLACEHOLDER, e.g. "/api/entities/{id}/image"

/** Full entity card on the external website. `{id}` is replaced with the encoded id. */
export const ENTITY_PAGE_URL = "https://kb.example.com/entity/{id}"; // PLACEHOLDER

// -----------------------------------------------------------------------

const fill = (template: string, id: string) => template.replace(/\{id\}/g, encodeURIComponent(id));

/** Link to the entity's full card on the external website. */
export function fullEntityUrl(id: string): string {
  return fill(ENTITY_PAGE_URL, id);
}

const attributesCache = new Map<string, Promise<EntityAttributes>>();
const imageCache = new Map<string, Promise<string | null>>();

/** Cache a lookup by id, forgetting failures so a later open retries. */
function cached<T>(cache: Map<string, Promise<T>>, id: string, load: () => Promise<T>): Promise<T> {
  let p = cache.get(id);
  if (!p) {
    p = load();
    cache.set(id, p);
    p.catch(() => cache.delete(id));
  }
  return p;
}

/** Fetch an entity's attributes from the knowledge base. */
export function fetchEntityAttributes(id: string): Promise<EntityAttributes> {
  return cached(attributesCache, id, async () => {
    const res = await fetch(fill(ENTITY_ATTRIBUTES_API, id));
    if (!res.ok) throw new Error(res.status === 404 ? "not found" : `${res.status} ${res.statusText}`);
    const data = (await res.json()) as Record<string, EntityAttribute>;
    if (!data || typeof data !== "object" || !data.title) throw new Error("response has no title");
    return data as EntityAttributes;
  });
}

/** Fetch the entity's image URL, or null when the entity (type) has none. */
export function fetchEntityImage(id: string): Promise<string | null> {
  if (!ENTITY_IMAGE_API) return Promise.resolve(null);
  const api = ENTITY_IMAGE_API;
  return cached(imageCache, id, async () => {
    const url = fill(api, id);
    const res = await fetch(url);
    if (!res.ok) return null;
    const type = res.headers.get("content-type") ?? "";
    if (type.startsWith("image/")) return url;
    if (type.includes("json")) {
      const body = (await res.json()) as { url?: string | null };
      return body?.url || null;
    }
    return null;
  }).catch(() => null);
}
