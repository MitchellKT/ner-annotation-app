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
  tags?: string[]; // free-form labels from the shared tag bank; omitted when empty
}

export type DocStatus = "unreviewed" | "in_progress" | "done";

export interface DocSummary {
  doc_id: string;
  index: number;
  type: string;
  source: string;
  status: DocStatus;
  n_entities: number;
  n_mentions: number;
  has_prediction: boolean;
}

export interface DocData {
  doc_id: string;
  index: number;
  type: string;
  source: string;
  text: string;
  status: DocStatus;
  entities: WireEntity[];
  prediction: WireEntity[];
}

export interface AppConfig {
  types: string[];
  warnings: string[];
}

// doc-type -> selected sources
export type Selection = Record<string, string[]>;

// Corpus metadata + this user's saved selection (source-selection screen).
export interface Meta {
  sourcesByType: Record<string, string[]>;
  counts: Record<string, Record<string, number>>;
  selection: Selection | null;
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
  tags: string[]; // always present client-side; serialized only when non-empty
  reviewed: boolean;
  origin: Origin;
}
