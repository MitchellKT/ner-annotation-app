import { create } from "zustand";
import { api, beaconSave } from "./api";
import type {
  AppConfig,
  DocData,
  DocStatus,
  DocSummary,
  Entity,
  Mention,
  Origin,
  WireEntity,
} from "./types";
import { toCodePoints } from "./lib/offsets";
import { findOccurrences } from "./lib/matches";
import { fragmentsKey, mergeFragments, toWireMention, wireFragments } from "./lib/mentions";
import type { WireMention } from "./types";

let _uid = 0;
const uid = (prefix: string) => `${prefix}${++_uid}`;

// ---- wire <-> client conversion ----------------------------------------
function signature(e: { type: string; uid?: string; mentions: WireMention[] }): string {
  const spans = e.mentions.map((m) => fragmentsKey(wireFragments(m))).sort().join(",");
  return `${e.type}|${e.uid ?? ""}|${spans}`;
}

function toClientEntities(doc: DocData): Entity[] {
  // Entities that exactly match an original prediction are treated as
  // unconfirmed predictions (faded) until reviewed; everything else is "user".
  const predSig = new Set(doc.prediction.map(signature));
  const allReviewed = doc.status === "done";
  return doc.entities.map((e) => {
    const isPred = predSig.has(signature(e));
    const origin: Origin = isPred ? "prediction" : "user";
    return {
      id: uid("e"),
      type: e.type,
      mentions: e.mentions.map((m) => ({
        id: uid("m"),
        fragments: wireFragments(m).map((f) => ({ start: f.start, end: f.end })),
      })),
      uid: e.uid,
      reviewed: allReviewed || origin === "user",
      origin,
    };
  });
}

function toWire(entities: Entity[]): WireEntity[] {
  return entities
    .filter((e) => e.mentions.length > 0)
    .map((e) => ({
      type: e.type,
      mentions: e.mentions.map((m) => toWireMention(m.fragments)),
      ...(e.uid ? { uid: e.uid } : {}),
    }));
}

function dedupeMentions(mentions: Mention[]): Mention[] {
  const seen = new Set<string>();
  const out: Mention[] = [];
  for (const m of mentions) {
    const key = fragmentsKey(m.fragments);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(m);
  }
  return out.sort(
    (a, b) => a.fragments[0].start - b.fragments[0].start || a.fragments[0].end - b.fragments[0].end
  );
}

// ---- store ---------------------------------------------------------------
export type SaveState = "idle" | "saving" | "saved" | "error";

interface Snapshot {
  entities: Entity[];
  status: DocStatus;
  activeEntityId: string | null;
}

interface State {
  config: AppConfig | null;
  summaries: DocSummary[];
  loading: boolean;
  error: string | null;

  docId: string | null;
  text: string;
  cps: string[];
  prediction: WireEntity[];
  entities: Entity[];
  status: DocStatus;

  activeEntityId: string | null;
  hoverEntityId: string | null;
  hoverMentionId: string | null;
  pendingMergeId: string | null; // first entity chosen for a merge
  uidPromptEntityId: string | null; // entity whose unique-id prompt is open
  selectionSpan: { start: number; end: number } | null; // current normalized text selection
  scrollTo: { start: number; nonce: number } | null; // request TextPanel to scroll/flash a span
  snap: boolean;
  autoMatch: boolean; // propagate a new mention to identical text elsewhere
  saveState: SaveState;

  undoStack: Snapshot[];
  redoStack: Snapshot[];

  // lifecycle
  init: () => Promise<void>;
  refreshSummaries: () => Promise<void>;
  loadDoc: (docId: string) => Promise<void>;
  gotoIndex: (index: number) => void;
  next: () => void;
  prev: () => void;
  nextUnreviewed: () => void;
  flushSave: () => void;

  // settings / transient ui
  setSelectionSpan: (span: { start: number; end: number } | null) => void;
  requestScrollTo: (start: number) => void;
  setSnap: (v: boolean) => void;
  setAutoMatch: (v: boolean) => void;
  setHoverEntity: (id: string | null) => void;
  setHoverMention: (id: string | null) => void;
  setActiveEntity: (id: string | null) => void;
  cycleActive: (dir: 1 | -1) => void;
  beginMerge: (id: string) => void;
  cancelMerge: () => void;
  openUidPrompt: (entityId: string) => void;
  closeUidPrompt: () => void;

  // mutations
  createEntity: (type: string, span: { start: number; end: number }) => void;
  addMention: (entityId: string, span: { start: number; end: number }) => void;
  addFragment: (entityId: string, mentionId: string, span: { start: number; end: number }) => void;
  removeFragment: (entityId: string, mentionId: string, fragmentIndex: number) => void;
  newEmptyEntity: () => void;
  removeMention: (entityId: string, mentionId: string) => void;
  reassignMention: (mentionId: string, fromId: string, toId: string) => void;
  setEntityType: (entityId: string, type: string) => void;
  setEntityUid: (entityId: string, uid: string | undefined) => void;
  deleteEntity: (entityId: string) => void;
  mergeEntities: (aId: string, bId: string) => void;
  splitMention: (entityId: string, mentionId: string) => void;
  toggleReviewed: (entityId: string) => void;
  acceptAll: () => void;
  markDone: () => void;
  revertToPrediction: () => void;
  undo: () => void;
  redo: () => void;
}

let saveTimer: ReturnType<typeof setTimeout> | null = null;

export const useStore = create<State>((set, get) => {
  function snapshot(): Snapshot {
    const s = get();
    return {
      entities: cloneEntities(s.entities),
      status: s.status,
      activeEntityId: s.activeEntityId,
    };
  }

  /** Apply an entity mutation: push undo, bump status, schedule autosave. */
  function mutate(fn: (entities: Entity[]) => Entity[], opts?: { activeId?: string | null }) {
    const before = snapshot();
    const s = get();
    const entities = fn(cloneEntities(s.entities));
    const status: DocStatus = s.status === "unreviewed" ? "in_progress" : s.status;
    set({
      entities,
      status,
      activeEntityId: opts && "activeId" in opts ? opts.activeId! : s.activeEntityId,
      undoStack: [...s.undoStack, before].slice(-100),
      redoStack: [],
    });
    scheduleSave();
  }

  /**
   * The spans a user-annotated span stands for: itself, plus — when
   * "auto-annotate repeats" is on — every other identical (Ctrl+F style,
   * case-sensitive) occurrence in the document.
   */
  function expandSpan(span: { start: number; end: number }): { start: number; end: number }[] {
    const s = get();
    return s.autoMatch ? [span, ...findOccurrences(s.cps, span)] : [span];
  }

  function scheduleSave() {
    if (saveTimer) clearTimeout(saveTimer);
    set({ saveState: "saving" });
    saveTimer = setTimeout(() => void doSave(), 500);
  }

  async function doSave() {
    const s = get();
    if (!s.docId) return;
    try {
      const summary = await api.saveDoc(s.docId, toWire(s.entities), s.status);
      set({
        saveState: "saved",
        summaries: get().summaries.map((d) => (d.doc_id === summary.doc_id ? summary : d)),
      });
    } catch (e) {
      set({ saveState: "error", error: String(e) });
    }
  }

  function flushSave() {
    if (saveTimer) {
      clearTimeout(saveTimer);
      saveTimer = null;
    }
    void doSave();
  }

  return {
    config: null,
    summaries: [],
    loading: false,
    error: null,

    docId: null,
    text: "",
    cps: [],
    prediction: [],
    entities: [],
    status: "unreviewed",

    activeEntityId: null,
    hoverEntityId: null,
    hoverMentionId: null,
    pendingMergeId: null,
    uidPromptEntityId: null,
    selectionSpan: null,
    scrollTo: null,
    snap: true,
    autoMatch: true,
    saveState: "idle",

    undoStack: [],
    redoStack: [],

    async init() {
      set({ loading: true });
      try {
        const [config, summaries] = await Promise.all([api.config(), api.listDocs()]);
        set({ config, summaries, loading: false });
        const first = summaries.find((d) => d.status !== "done") ?? summaries[0];
        if (first) await get().loadDoc(first.doc_id);
      } catch (e) {
        set({ error: String(e), loading: false });
      }
    },

    async refreshSummaries() {
      set({ summaries: await api.listDocs() });
    },

    async loadDoc(docId: string) {
      flushSave(); // persist the doc we're leaving
      try {
        const doc = await api.getDoc(docId);
        const entities = toClientEntities(doc);
        set({
          docId: doc.doc_id,
          text: doc.text,
          cps: toCodePoints(doc.text),
          prediction: doc.prediction,
          entities,
          status: doc.status,
          activeEntityId: entities[0]?.id ?? null,
          hoverEntityId: null,
          hoverMentionId: null,
          pendingMergeId: null,
          uidPromptEntityId: null,
          selectionSpan: null,
          undoStack: [],
          redoStack: [],
          saveState: "idle",
        });
      } catch (e) {
        set({ error: String(e) });
      }
    },

    gotoIndex(index: number) {
      const s = get();
      const target = s.summaries[index];
      if (target) void s.loadDoc(target.doc_id);
    },
    next() {
      const s = get();
      const i = s.summaries.findIndex((d) => d.doc_id === s.docId);
      if (i >= 0 && i < s.summaries.length - 1) s.gotoIndex(i + 1);
    },
    prev() {
      const s = get();
      const i = s.summaries.findIndex((d) => d.doc_id === s.docId);
      if (i > 0) s.gotoIndex(i - 1);
    },
    nextUnreviewed() {
      const s = get();
      const i = s.summaries.findIndex((d) => d.doc_id === s.docId);
      const after = s.summaries.slice(i + 1).find((d) => d.status !== "done");
      const any = after ?? s.summaries.find((d) => d.status !== "done");
      if (any) void s.loadDoc(any.doc_id);
    },
    flushSave,

    setSelectionSpan: (span) => set({ selectionSpan: span }),
    requestScrollTo: (start) => set({ scrollTo: { start, nonce: Date.now() } }),
    setSnap: (v) => set({ snap: v }),
    setAutoMatch: (v) => set({ autoMatch: v }),
    setHoverEntity: (id) => set({ hoverEntityId: id }),
    setHoverMention: (id) => set({ hoverMentionId: id }),
    setActiveEntity: (id) => set({ activeEntityId: id }),
    cycleActive(dir) {
      const s = get();
      if (s.entities.length === 0) return;
      const i = s.entities.findIndex((e) => e.id === s.activeEntityId);
      const ni = (i + dir + s.entities.length) % s.entities.length;
      set({ activeEntityId: s.entities[ni].id });
    },
    beginMerge: (id) => set({ pendingMergeId: id }),
    cancelMerge: () => set({ pendingMergeId: null }),
    openUidPrompt: (entityId) => set({ uidPromptEntityId: entityId }),
    closeUidPrompt: () => set({ uidPromptEntityId: null }),

    createEntity(type, span) {
      const id = uid("e");
      const entity: Entity = {
        id,
        type,
        mentions: dedupeMentions(
          expandSpan(span).map((sp) => ({ id: uid("m"), fragments: [{ start: sp.start, end: sp.end }] }))
        ),
        reviewed: true,
        origin: "user",
      };
      mutate((entities) => [...entities, entity], { activeId: id });
      // Prompt for the (optional) unique identifier right after creation;
      // the user can dismiss it with Escape.
      set({ uidPromptEntityId: id });
    },

    addMention(entityId, span) {
      const added = expandSpan(span).map((sp) => ({
        id: uid("m"),
        fragments: [{ start: sp.start, end: sp.end }],
      }));
      mutate((entities) =>
        entities.map((e) =>
          e.id === entityId
            ? { ...e, mentions: dedupeMentions([...e.mentions, ...added]), reviewed: true }
            : e
        ),
        { activeId: entityId }
      );
    },

    addFragment(entityId, mentionId, span) {
      mutate((entities) =>
        entities.map((e) =>
          e.id === entityId
            ? {
                ...e,
                mentions: dedupeMentions(
                  e.mentions.map((m) =>
                    m.id === mentionId
                      ? { ...m, fragments: mergeFragments([...m.fragments, span]) }
                      : m
                  )
                ),
                reviewed: true,
              }
            : e
        ),
        { activeId: entityId }
      );
    },

    removeFragment(entityId, mentionId, fragmentIndex) {
      mutate((entities) =>
        entities
          .map((e) =>
            e.id === entityId
              ? {
                  ...e,
                  mentions: e.mentions
                    .map((m) =>
                      m.id === mentionId
                        ? { ...m, fragments: m.fragments.filter((_, i) => i !== fragmentIndex) }
                        : m
                    )
                    .filter((m) => m.fragments.length > 0),
                }
              : e
          )
          .filter((e) => e.mentions.length > 0)
      );
    },

    newEmptyEntity() {
      const id = uid("e");
      const entity: Entity = {
        id,
        type: get().config?.types[0] ?? "PER",
        mentions: [],
        reviewed: true,
        origin: "user",
      };
      mutate((entities) => [...entities, entity], { activeId: id });
      set({ uidPromptEntityId: id });
    },

    removeMention(entityId, mentionId) {
      mutate((entities) =>
        entities
          .map((e) =>
            e.id === entityId ? { ...e, mentions: e.mentions.filter((m) => m.id !== mentionId) } : e
          )
          .filter((e) => e.mentions.length > 0)
      );
    },

    reassignMention(mentionId, fromId, toId) {
      if (fromId === toId) return;
      mutate((entities) => {
        const from = entities.find((e) => e.id === fromId);
        const moved = from?.mentions.find((m) => m.id === mentionId);
        if (!moved) return entities;
        return entities
          .map((e) => {
            if (e.id === fromId) return { ...e, mentions: e.mentions.filter((m) => m.id !== mentionId) };
            if (e.id === toId)
              return { ...e, mentions: dedupeMentions([...e.mentions, moved]), reviewed: true };
            return e;
          })
          .filter((e) => e.mentions.length > 0);
      }, { activeId: toId });
    },

    setEntityType(entityId, type) {
      mutate((entities) => entities.map((e) => (e.id === entityId ? { ...e, type, reviewed: true } : e)));
    },

    setEntityUid(entityId, entityUid) {
      const trimmed = entityUid?.trim() || undefined;
      mutate((entities) =>
        entities.map((e) => (e.id === entityId ? { ...e, uid: trimmed, reviewed: true } : e))
      );
    },

    deleteEntity(entityId) {
      const s = get();
      const remaining = s.entities.filter((e) => e.id !== entityId);
      mutate(() => remaining, {
        activeId: s.activeEntityId === entityId ? remaining[0]?.id ?? null : s.activeEntityId,
      });
    },

    mergeEntities(aId, bId) {
      if (aId === bId) return;
      mutate((entities) => {
        const a = entities.find((e) => e.id === aId);
        const b = entities.find((e) => e.id === bId);
        if (!a || !b) return entities;
        return entities
          .map((e) =>
            e.id === aId
              ? { ...e, mentions: dedupeMentions([...a.mentions, ...b.mentions]), reviewed: true }
              : e
          )
          .filter((e) => e.id !== bId);
      }, { activeId: aId });
      set({ pendingMergeId: null });
    },

    splitMention(entityId, mentionId) {
      const newId = uid("e");
      mutate((entities) => {
        const src = entities.find((e) => e.id === entityId);
        const m = src?.mentions.find((x) => x.id === mentionId);
        if (!src || !m) return entities;
        const newEntity: Entity = {
          id: newId,
          type: src.type,
          mentions: [m],
          reviewed: true,
          origin: "user",
        };
        const out = entities
          .map((e) => (e.id === entityId ? { ...e, mentions: e.mentions.filter((x) => x.id !== mentionId) } : e))
          .filter((e) => e.mentions.length > 0);
        return [...out, newEntity];
      }, { activeId: newId });
    },

    toggleReviewed(entityId) {
      mutate((entities) =>
        entities.map((e) => (e.id === entityId ? { ...e, reviewed: !e.reviewed } : e))
      );
    },

    acceptAll() {
      mutate((entities) => entities.map((e) => ({ ...e, reviewed: true })));
    },

    markDone() {
      const before = snapshot();
      const s = get();
      set({
        status: "done",
        entities: s.entities.map((e) => ({ ...e, reviewed: true })),
        undoStack: [...s.undoStack, before].slice(-100),
        redoStack: [],
      });
      flushSave();
      get().nextUnreviewed();
    },

    revertToPrediction() {
      const s = get();
      const fakeDoc: DocData = {
        doc_id: s.docId ?? "",
        index: 0,
        text: s.text,
        status: "unreviewed",
        entities: s.prediction,
        prediction: s.prediction,
      };
      const entities = toClientEntities(fakeDoc);
      mutate(() => entities, { activeId: entities[0]?.id ?? null });
    },

    undo() {
      const s = get();
      if (s.undoStack.length === 0) return;
      const prev = s.undoStack[s.undoStack.length - 1];
      set({
        entities: cloneEntities(prev.entities),
        status: prev.status,
        activeEntityId: prev.activeEntityId,
        undoStack: s.undoStack.slice(0, -1),
        redoStack: [...s.redoStack, snapshot()],
      });
      scheduleSave();
    },

    redo() {
      const s = get();
      if (s.redoStack.length === 0) return;
      const nxt = s.redoStack[s.redoStack.length - 1];
      set({
        entities: cloneEntities(nxt.entities),
        status: nxt.status,
        activeEntityId: nxt.activeEntityId,
        redoStack: s.redoStack.slice(0, -1),
        undoStack: [...s.undoStack, snapshot()],
      });
      scheduleSave();
    },
  };
});

function cloneEntities(entities: Entity[]): Entity[] {
  return entities.map((e) => ({
    ...e,
    mentions: e.mentions.map((m) => ({ ...m, fragments: m.fragments.map((f) => ({ ...f })) })),
  }));
}

// Persist on tab close.
if (typeof window !== "undefined") {
  window.addEventListener("beforeunload", () => {
    const s = useStore.getState();
    if (s.docId && s.saveState !== "saved") {
      beaconSave(s.docId, toWire(s.entities), s.status);
    }
  });
}
