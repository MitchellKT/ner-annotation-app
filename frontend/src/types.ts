// ---- On-disk / wire shapes (match the backend JSONL schema) ----
export interface WireSpan {
  start: number; // code-point offset, inclusive
  end: number; // code-point offset, exclusive
}
// A continuous mention is a plain {start,end}; a non-continuous mention is an
// ordered list of non-overlapping fragments (e.g. "Annie … Washington").
export type WireMention = WireSpan | { fragments: WireSpan[] };
export interface WireEntity {
  type: string;
  mentions: WireMention[];
  uid?: string; // optional external unique identifier (e.g. a KB / Wikidata id)
}

export type DocStatus = "unreviewed" | "in_progress" | "done";

export interface DocSummary {
  doc_id: string;
  index: number;
  status: DocStatus;
  n_entities: number;
  n_mentions: number;
  has_prediction: boolean;
}

export interface DocData {
  doc_id: string;
  index: number;
  text: string;
  status: DocStatus;
  entities: WireEntity[];
  prediction: WireEntity[];
}

export interface AppConfig {
  types: string[];
  warnings: string[];
}

// ---- session / workspace ----
export interface SessionInfo {
  slug: string;
  name: string;
  has_workspace: boolean;
}

export interface WorkspaceInfo {
  filename: string | null;
  types: string[];
  uploaded_at: number | null;
  n_docs: number;
  n_done: number;
  warnings: string[];
}

// ---- Client-side model (stable ids; origin/reviewed are session-only) ----
export type Origin = "prediction" | "user";

export interface Mention {
  id: string;
  // One or more sorted, non-overlapping spans; length > 1 = non-continuous.
  fragments: { start: number; end: number }[];
}

export interface Entity {
  id: string;
  type: string;
  mentions: Mention[];
  uid?: string; // optional external unique identifier
  reviewed: boolean;
  origin: Origin;
}
