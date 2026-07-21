import type {
  AppConfig,
  Comment,
  DocData,
  DocSummary,
  DocStatus,
  Meta,
  Selection,
  WireEntity,
} from "./types";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${detail}`);
  }
  return res.json() as Promise<T>;
}

const enc = encodeURIComponent;
const userBase = (user: string) => `/api/users/${enc(user)}`;

export const api = {
  config: () => fetch("/api/config").then((r) => json<AppConfig>(r)),

  meta: (user: string) => fetch(`${userBase(user)}/meta`).then((r) => json<Meta>(r)),

  // The tag bank is shared by every annotator, so it isn't user-scoped.
  tags: () => fetch("/api/tags").then((r) => json<{ tags: string[] }>(r)),

  createTag: (name: string) =>
    fetch("/api/tags", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }).then((r) => json<{ tag: string; tags: string[] }>(r)),

  // Document comments are one shared thread per document, like the tag bank —
  // not user-scoped; the author rides along in the POST body.
  comments: (docId: string) =>
    fetch(`/api/docs/${enc(docId)}/comments`).then((r) => json<{ comments: Comment[] }>(r)),

  addComment: (docId: string, author: string, text: string) =>
    fetch(`/api/docs/${enc(docId)}/comments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ author, text }),
    }).then((r) => json<{ comments: Comment[] }>(r)),

  setSelection: (user: string, selection: Selection) =>
    fetch(`${userBase(user)}/selection`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selection }),
    }).then((r) => json<{ selection: Selection }>(r)),

  listDocs: (user: string) => fetch(`${userBase(user)}/docs`).then((r) => json<DocSummary[]>(r)),

  getDoc: (user: string, docId: string) =>
    fetch(`${userBase(user)}/docs/${enc(docId)}`).then((r) => json<DocData>(r)),

  saveDoc: (user: string, docId: string, entities: WireEntity[], status: DocStatus) =>
    fetch(`${userBase(user)}/docs/${enc(docId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ entities, status }),
    }).then((r) => json<DocSummary>(r)),
};

/** Fire-and-forget save that survives page unload (used on window close). */
export function beaconSave(
  user: string,
  docId: string,
  entities: WireEntity[],
  status: DocStatus
): void {
  const body = JSON.stringify({ entities, status });
  const blob = new Blob([body], { type: "application/json" });
  navigator.sendBeacon(`${userBase(user)}/docs/${enc(docId)}`, blob);
}
