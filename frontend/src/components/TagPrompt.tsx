import { useEffect, useMemo, useState } from "react";
import { useStore } from "../store";
import { cpSlice } from "../lib/offsets";
import { colorForType } from "../colors";

/**
 * Tag picker for one entity, opened from the 🏷 button on its card.
 *
 * A single free-form field doubles as filter and new-tag input: typing narrows
 * the shared tag bank, and when what you typed isn't in the bank yet the last
 * option creates it. Tags are added verbatim (any script), so the list is
 * filtered case-insensitively but nothing is folded on the way in.
 *
 * The dialog stays open after each pick so several tags can be added in a row;
 * Escape (or clicking outside) closes it.
 */
// Stable identity, so a tagless entity doesn't invalidate the memo every render.
const NO_TAGS: string[] = [];

export function TagPrompt() {
  const entityId = useStore((s) => s.tagPromptEntityId);
  const entity = useStore((s) => s.entities.find((e) => e.id === s.tagPromptEntityId));
  const cps = useStore((s) => s.cps);
  const tagBank = useStore((s) => s.tagBank);
  const addEntityTag = useStore((s) => s.addEntityTag);
  const removeEntityTag = useStore((s) => s.removeEntityTag);
  const closeTagPrompt = useStore((s) => s.closeTagPrompt);

  const [query, setQuery] = useState("");
  const [highlight, setHighlight] = useState(0);

  // Close if the entity vanished (deleted / undo) while the picker was open.
  useEffect(() => {
    if (entityId && !entity) closeTagPrompt();
  }, [entityId, entity, closeTagPrompt]);

  const trimmed = query.trim();
  const current = entity?.tags ?? NO_TAGS;

  // Bank tags not already on this entity, narrowed by the query. The exact
  // match (if any) is floated to the top so Enter picks it over a prefix hit.
  const suggestions = useMemo(() => {
    const needle = trimmed.toLocaleLowerCase();
    const available = tagBank.filter((t) => !current.includes(t));
    if (!needle) return available;
    return available
      .filter((t) => t.toLocaleLowerCase().includes(needle))
      .sort((a, b) => Number(b.toLocaleLowerCase() === needle) - Number(a.toLocaleLowerCase() === needle));
  }, [tagBank, current, trimmed]);

  // Offer creation unless the typed text is already a tag (here or in the bank).
  const canCreate =
    trimmed.length > 0 && !current.includes(trimmed) && !tagBank.includes(trimmed);
  const optionCount = suggestions.length + (canCreate ? 1 : 0);
  const index = Math.min(highlight, Math.max(optionCount - 1, 0));

  useEffect(() => setHighlight(0), [trimmed]);

  if (!entity) return null;

  function add(tag: string) {
    addEntityTag(entity!.id, tag);
    setQuery(""); // ready for the next tag
    setHighlight(0);
  }

  function commitHighlighted() {
    if (index < suggestions.length) add(suggestions[index]);
    else if (canCreate) add(trimmed);
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") {
      e.preventDefault();
      commitHighlighted();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      if (optionCount > 0) setHighlight((i) => (i + 1) % optionCount);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (optionCount > 0) setHighlight((i) => (i - 1 + optionCount) % optionCount);
    } else if (e.key === "Backspace" && query === "" && current.length > 0) {
      // Empty field: Backspace peels off the last tag, as in most tag inputs.
      e.preventDefault();
      removeEntityTag(entity!.id, current[current.length - 1]);
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      closeTagPrompt();
    }
  }

  const firstMention = entity.mentions[0];
  const surface = firstMention
    ? firstMention.fragments.map((f) => cpSlice(cps, f.start, f.end)).join(" ‥ ")
    : "";

  return (
    <div className="overlay uid-overlay" onClick={closeTagPrompt}>
      <div className="uid-card tag-card" onClick={(e) => e.stopPropagation()}>
        <div className="uid-head">
          <span className="type-chip" style={{ background: colorForType(entity.type) }}>
            {entity.type}
          </span>
          {surface && (
            <strong>
              “<bdi>{surface.slice(0, 60)}</bdi>”
            </strong>
          )}
        </div>

        <label className="uid-label" htmlFor="tag-input">
          Tags <span style={{ color: "var(--muted)" }}>(shared between annotators)</span>
        </label>

        {current.length > 0 && (
          <div className="tag-list">
            {current.map((t) => (
              <span key={t} className="tag-chip">
                <bdi>{t}</bdi>
                <span
                  className="x"
                  title={`remove tag ${t}`}
                  onClick={() => removeEntityTag(entity.id, t)}
                >
                  ×
                </span>
              </span>
            ))}
          </div>
        )}

        <input
          id="tag-input"
          className="uid-input"
          autoFocus
          value={query}
          placeholder="type to search or create a tag — Enter to add, Esc to close"
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onKeyDown}
        />

        <div className="tag-options">
          {suggestions.map((t, i) => (
            <button
              key={t}
              className={"tag-option" + (i === index ? " active" : "")}
              onMouseEnter={() => setHighlight(i)}
              onClick={() => add(t)}
            >
              <bdi>{t}</bdi>
            </button>
          ))}
          {canCreate && (
            <button
              className={"tag-option create" + (index === suggestions.length ? " active" : "")}
              onMouseEnter={() => setHighlight(suggestions.length)}
              onClick={() => add(trimmed)}
            >
              + Create “<bdi>{trimmed}</bdi>”
            </button>
          )}
          {optionCount === 0 && (
            <span className="tag-empty">
              {trimmed ? "already tagged" : "no tags yet — type one to create it"}
            </span>
          )}
        </div>

        <div className="uid-actions">
          <button className="primary" onClick={closeTagPrompt} title="close (Esc)">
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
