import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useStore } from "../store";
import { cpSlice } from "../lib/offsets";
import { colorForIndex, colorForType } from "../colors";

/**
 * A small floating action bar that pops up right above a mention when it is
 * clicked in the text, exposing the mention/entity actions (remove, split,
 * retype, confirm, tag, id, delete) without a trip to the entity card.
 *
 * It anchors itself to the clicked text segment (`data-start`) and closes on
 * Escape, an outside click, or scrolling the document.
 */
export function MentionMenu() {
  const menu = useStore((s) => s.mentionMenu);
  const entities = useStore((s) => s.entities);
  const cps = useStore((s) => s.cps);
  const types = useStore((s) => s.config?.types ?? ["PER", "LOC", "ORG", "TIME"]);

  const closeMentionMenu = useStore((s) => s.closeMentionMenu);
  const removeMention = useStore((s) => s.removeMention);
  const splitMention = useStore((s) => s.splitMention);
  const toggleReviewed = useStore((s) => s.toggleReviewed);
  const setEntityType = useStore((s) => s.setEntityType);
  const openTagPrompt = useStore((s) => s.openTagPrompt);
  const openUidPrompt = useStore((s) => s.openUidPrompt);
  const deleteEntity = useStore((s) => s.deleteEntity);

  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);

  const entityIndex = menu ? entities.findIndex((e) => e.id === menu.entityId) : -1;
  const entity = entityIndex >= 0 ? entities[entityIndex] : undefined;
  const mention = entity?.mentions.find((m) => m.id === menu?.mentionId);

  // Close if the mention/entity vanished (removed, split, undo) while open.
  useEffect(() => {
    if (menu && !mention) closeMentionMenu();
  }, [menu, mention, closeMentionMenu]);

  // Anchor above the clicked segment; flip below if there isn't room.
  useLayoutEffect(() => {
    if (!menu || !ref.current) return;
    const anchor = document.querySelector<HTMLElement>(
      `.doc-text [data-start="${menu.anchorStart}"]`
    );
    if (!anchor) return;
    const a = anchor.getBoundingClientRect();
    const m = ref.current.getBoundingClientRect();
    const left = Math.max(8, Math.min(a.left + a.width / 2 - m.width / 2, window.innerWidth - m.width - 8));
    const above = a.top - m.height - 8;
    const top = above >= 8 ? above : a.bottom + 8;
    setPos({ left, top });
  }, [menu, entity?.type, entity?.reviewed, entity?.uid]);

  // Dismiss on outside click or any scroll (the anchor position goes stale).
  useEffect(() => {
    if (!menu) return;
    function onDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) closeMentionMenu();
    }
    function onScroll() {
      closeMentionMenu();
    }
    document.addEventListener("mousedown", onDown);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onScroll);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onScroll);
    };
  }, [menu, closeMentionMenu]);

  if (!menu || !entity || !mention) return null;

  const color = colorForIndex(entityIndex);
  const surface = mention.fragments.map((f) => cpSlice(cps, f.start, f.end)).join(" ‥ ");
  const typeOptions = types.includes(entity.type) ? types : [entity.type, ...types];
  const canSplit = entity.mentions.length > 1;

  return (
    <div
      ref={ref}
      className="mention-menu"
      style={{ left: pos?.left ?? -9999, top: pos?.top ?? -9999, visibility: pos ? "visible" : "hidden" }}
      // Keep a click inside the bar from bubbling to the text (which would
      // re-open / move the menu) and from clearing the selection.
      onClick={(e) => e.stopPropagation()}
      onMouseDown={(e) => e.stopPropagation()}
    >
      <span className="mm-swatch" style={{ background: color.strong }} />
      <span className="mm-index" title={`entity #${entityIndex + 1}`}>#{entityIndex + 1}</span>
      <select
        className="type-chip mm-type"
        style={{ background: colorForType(entity.type) }}
        value={entity.type}
        title="change entity type"
        onChange={(e) => setEntityType(entity.id, e.target.value)}
      >
        {typeOptions.map((t) => (
          <option key={t} value={t} style={{ background: "#fff", color: "#1c2430" }}>
            {t}
          </option>
        ))}
      </select>
      <span className="mm-surface" title={surface}>
        “<bdi>{surface.slice(0, 32) || "∅"}</bdi>”
      </span>

      <span className="mm-sep" />

      <button
        className={"icon-btn" + (entity.reviewed ? " on" : "")}
        title="confirm / unconfirm entity (r)"
        onClick={() => toggleReviewed(entity.id)}
      >
        ✓
      </button>
      <button
        className={"icon-btn" + (entity.tags.length ? " on-tag" : "")}
        title={entity.tags.length ? `tags: ${entity.tags.join(", ")} — edit` : "add tags"}
        onClick={() => {
          openTagPrompt(entity.id);
          closeMentionMenu();
        }}
      >
        🏷
      </button>
      <button
        className="icon-btn"
        title={entity.uid ? `unique id: ${entity.uid} — edit` : "set unique identifier"}
        onClick={() => {
          openUidPrompt(entity.id);
          closeMentionMenu();
        }}
      >
        id
      </button>
      <button
        className="icon-btn"
        title="split this mention into its own entity (s)"
        disabled={!canSplit}
        onClick={() => {
          splitMention(entity.id, mention.id);
          closeMentionMenu();
        }}
      >
        ⑃
      </button>

      <span className="mm-sep" />

      <button
        className="icon-btn mm-remove"
        title="remove this mention (Del)"
        onClick={() => {
          removeMention(entity.id, mention.id);
          closeMentionMenu();
        }}
      >
        ✕ mention
      </button>
      <button
        className="icon-btn mm-delete"
        title="delete the whole entity"
        onClick={() => {
          deleteEntity(entity.id);
          closeMentionMenu();
        }}
      >
        🗑
      </button>
    </div>
  );
}
