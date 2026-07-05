import { useEffect, useState } from "react";
import { useStore } from "../store";
import { cpSlice } from "../lib/offsets";
import { colorForType } from "../colors";

/**
 * Small dialog shown right after an entity is created (and from the ✎ id
 * button on a card): asks for the entity's optional unique identifier.
 * Enter saves, Escape (or clicking outside) skips without setting anything.
 */
export function UidPrompt() {
  const entityId = useStore((s) => s.uidPromptEntityId);
  const entity = useStore((s) => s.entities.find((e) => e.id === s.uidPromptEntityId));
  const cps = useStore((s) => s.cps);
  const setEntityUid = useStore((s) => s.setEntityUid);
  const closeUidPrompt = useStore((s) => s.closeUidPrompt);

  const [value, setValue] = useState(entity?.uid ?? "");

  // Close if the entity vanished (deleted / undo) while the prompt was open.
  useEffect(() => {
    if (entityId && !entity) closeUidPrompt();
  }, [entityId, entity, closeUidPrompt]);

  if (!entity) return null;

  const firstMention = entity.mentions[0];
  const surface = firstMention
    ? firstMention.fragments.map((f) => cpSlice(cps, f.start, f.end)).join(" ‥ ")
    : "";

  function save() {
    setEntityUid(entity!.id, value);
    closeUidPrompt();
  }

  return (
    <div className="overlay uid-overlay" onClick={closeUidPrompt}>
      <div className="uid-card" onClick={(e) => e.stopPropagation()}>
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
        <label className="uid-label" htmlFor="uid-input">
          Unique identifier <span style={{ color: "var(--muted)" }}>(optional)</span>
        </label>
        <input
          id="uid-input"
          className="uid-input"
          autoFocus
          value={value}
          placeholder="e.g. Q76, kb:obama-1 — Enter to save, Esc to skip"
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              save();
            } else if (e.key === "Escape") {
              e.preventDefault();
              e.stopPropagation();
              closeUidPrompt();
            }
          }}
        />
        <div className="uid-actions">
          <button onClick={closeUidPrompt} title="skip without setting an id (Esc)">
            Skip
          </button>
          <button className="primary" onClick={save} title="save (Enter)">
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
