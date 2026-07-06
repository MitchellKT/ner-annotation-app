import type {
  AppConfig,
  DocData,
  DocSummary,
  DocStatus,
  SessionInfo,
  WorkspaceInfo,
  WireEntity,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new ApiError(res.status, `${res.status} ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  // ---- session / workspace ----
  whoami: () => fetch("/api/session").then((r) => json<SessionInfo>(r)),
  identify: (name: string) =>
    fetch("/api/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }).then((r) => json<SessionInfo>(r)),
  signOut: () => fetch("/api/session", { method: "DELETE" }).then((r) => json<{ ok: boolean }>(r)),
  workspace: () => fetch("/api/workspace").then((r) => json<WorkspaceInfo>(r)),
  uploadWorkspace: (file: File, types: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("types", types);
    return fetch("/api/workspace", { method: "POST", body: form }).then((r) =>
      json<WorkspaceInfo>(r)
    );
  },
  downloadOutputUrl: () => "/api/workspace/output",

  // ---- annotation ----
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
