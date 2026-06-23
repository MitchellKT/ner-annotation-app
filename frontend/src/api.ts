import type { AppConfig, DocData, DocSummary, DocStatus, WireEntity } from "./types";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  config: () => fetch("/api/config").then((r) => json<AppConfig>(r)),
  listDocs: () => fetch("/api/docs").then((r) => json<DocSummary[]>(r)),
  getDoc: (docId: string) =>
    fetch(`/api/docs/${encodeURIComponent(docId)}`).then((r) => json<DocData>(r)),
  saveDoc: (docId: string, entities: WireEntity[], status: DocStatus) =>
    fetch(`/api/docs/${encodeURIComponent(docId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ entities, status }),
    }).then((r) => json<DocSummary>(r)),
};

/** Fire-and-forget save that survives page unload (used on window close). */
export function beaconSave(docId: string, entities: WireEntity[], status: DocStatus): void {
  const body = JSON.stringify({ entities, status });
  const blob = new Blob([body], { type: "application/json" });
  navigator.sendBeacon(`/api/docs/${encodeURIComponent(docId)}`, blob);
}
