// ---- On-disk / wire shapes (match the backend JSONL schema) ----
export interface WireSpan {
  start: number; // code-point offset, inclusive
  end: number; // code-point offset, exclusive
}
// A continuous mention is a plain {start,end}; a non-continuous mention is an
// ordered list of non-overlapping fragments (e.g. "Annie … Washington"). Either
// form may carry `relative: true` when the mention refers to its entity through
// a relation to another (e.g. "father of Abraham"); the flag is omitted when
// false, so ordinary mentions keep the original schema.
export type WireMention =
  | (WireSpan & { relative?: boolean })
  | { fragments: WireSpan[]; relative?: boolean };
export interface WireEntity {
  type: string;
  mentions: WireMention[];
  uid?: string; // optional external unique identifier (e.g. a KB / Wikidata id)
  tags?: string[]; // free-form labels from the shared tag bank; omitted when empty
}

// A document-level note. Comments are shared by every annotator, so `author`
// is the username of whoever wrote it.
export interface Comment {
  author: string;
  text: string;
  created_at: string; // ISO-8601 UTC, e.g. "2026-07-21T09:12:04Z"
}

export type DocStatus = "unreviewed" | "in_progress" | "done";

export interface DocSummary {
  doc_id: string;
  index: number;
  type: string;
  category: string;
  source: string;
  status: DocStatus;
  n_entities: number;
  n_mentions: number;
  n_comments: number;
  has_prediction: boolean;
}

export interface DocData {
  doc_id: string;
  index: number;
  type: string;
  category: string;
  source: string;
  text: string;
  status: DocStatus;
  entities: WireEntity[];
  prediction: WireEntity[];
  comments: Comment[];
}

export interface AppConfig {
  types: string[];
  warnings: string[];
}

// doc-type -> selected sources. A category is only a display grouping of the
// sources it contains, so the selection stays keyed by (type, source).
export type Selection = Record<string, string[]>;

// Corpus metadata + this user's saved selection (source-selection screen).
export interface Meta {
  sourcesByType: Record<string, string[]>;
  // type -> category -> sources: the grouping shown on the selection screen.
  categoriesByType: Record<string, Record<string, string[]>>;
  counts: Record<string, Record<string, number>>;
  selection: Selection | null;
}

// ---- Client-side model (stable ids; origin/reviewed are session-only) ----
export type Origin = "prediction" | "user";

export interface Mention {
  id: string;
  // One or more sorted, non-overlapping spans; length > 1 = non-continuous.
  fragments: { start: number; end: number }[];
  // True when the mention names its entity only through a relation to another
  // (e.g. "father of Abraham", "John's secretary"). Defaults to false.
  relative: boolean;
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
