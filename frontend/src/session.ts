import { create } from "zustand";
import { api, ApiError } from "./api";
import type { SessionInfo, WorkspaceInfo } from "./types";

// The app is a small state machine in front of the annotator:
//   booting -> name (no session) -> upload (session, no file) -> ready
export type Phase = "booting" | "name" | "upload" | "ready";

interface SessionState {
  phase: Phase;
  session: SessionInfo | null;
  workspace: WorkspaceInfo | null;
  busy: boolean;
  error: string | null;

  bootstrap: () => Promise<void>;
  identify: (name: string) => Promise<void>;
  upload: (file: File, types: string) => Promise<void>;
  signOut: () => Promise<void>;
  replaceFile: () => void; // go back to the upload screen to swap files
  handleAuthError: (status: number) => void;
}

export const useSession = create<SessionState>((set, get) => ({
  phase: "booting",
  session: null,
  workspace: null,
  busy: false,
  error: null,

  async bootstrap() {
    try {
      const session = await api.whoami();
      if (!session.has_workspace) {
        set({ session, workspace: null, phase: "upload" });
        return;
      }
      const workspace = await api.workspace().catch(() => null);
      set({ session, workspace, phase: "ready" });
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        set({ session: null, phase: "name" });
      } else {
        set({ error: String(e), phase: "name" });
      }
    }
  },

  async identify(name) {
    set({ busy: true, error: null });
    try {
      const session = await api.identify(name);
      if (session.has_workspace) {
        const workspace = await api.workspace().catch(() => null);
        set({ session, workspace, phase: "ready", busy: false });
      } else {
        set({ session, workspace: null, phase: "upload", busy: false });
      }
    } catch (e) {
      set({ error: humanize(e), busy: false });
    }
  },

  async upload(file, types) {
    set({ busy: true, error: null });
    try {
      const workspace = await api.uploadWorkspace(file, types);
      const session = get().session;
      set({
        workspace,
        session: session ? { ...session, has_workspace: true } : session,
        phase: "ready",
        busy: false,
      });
    } catch (e) {
      set({ error: humanize(e), busy: false });
    }
  },

  async signOut() {
    try {
      await api.signOut();
    } finally {
      set({ session: null, workspace: null, phase: "name", error: null });
    }
  },

  replaceFile() {
    set({ phase: "upload", error: null });
  },

  handleAuthError(status) {
    // 401 => session gone (re-identify); 409 => workspace gone (re-upload).
    if (status === 401) set({ session: null, workspace: null, phase: "name" });
    else if (status === 409) set({ phase: "upload" });
  },
}));

function humanize(e: unknown): string {
  if (e instanceof ApiError) {
    // Strip the leading "<status> " and any FastAPI JSON envelope.
    const msg = e.message.replace(/^\d+\s+/, "");
    try {
      const parsed = JSON.parse(msg);
      if (parsed && typeof parsed.detail === "string") return parsed.detail;
    } catch {
      /* not JSON */
    }
    return msg;
  }
  return String(e);
}
