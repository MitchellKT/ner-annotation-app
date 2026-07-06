import { useEffect, useRef, useState } from "react";
import { useStore } from "../store";
import { colorForIndex, colorForType } from "../colors";
import type { Entity } from "../types";
import { MentionChip } from "./MentionChip";
import { fragmentsKey } from "../lib/mentions";

interface Props {
  entity: Entity;
  index: number;
  predictionSpans: Set<string>;
}

export function EntityCard({ entity, index, predictionSpans }: Props) {
  const types = useStore((s) => s.config?.types ?? ["PER", "LOC", "ORG", "TIME"]);
  const activeEntityId = useStore((s) => s.activeEntityId);
  const pendingMergeId = useStore((s) => s.pendingMergeId);
  const setActiveEntity = useStore((s) => s.setActiveEntity);
  const setEntityType = useStore((s) => s.setEntityType);
  const toggleReviewed = useStore((s) => s.toggleReviewed);
  const deleteEntity = useStore((s) => s.deleteEntity);
  const beginMerge = useStore((s) => s.beginMerge);
  const cancelMerge = useStore((s) => s.cancelMerge);
  const mergeEntities = useStore((s) => s.mergeEntities);
  const reassignMention = useStore((s) => s.reassignMention);
  const splitMention = useStore((s) => s.splitMention);
  const setDraggingMention = useStore((s) => s.setDraggingMention);
  const openUidPrompt = useStore((s) => s.openUidPrompt);
  const setHoverEntity = useStore((s) => s.setHoverEntity);
  const selectionSpan = useStore((s) => s.selectionSpan);
  const addMention = useStore((s) => s.addMention);
  const setSelectionSpan = useStore((s) => s.setSelectionSpan);

  const ref = useRef<HTMLDivElement>(null);
  // True while something is being dragged over this card — drives the drop-target
  // highlight so the user can see where a reassign/merge will land before release.
  const [dragOver, setDragOver] = useState(false);
  const color = colorForIndex(index);
  const active = entity.id === activeEntityId;
  const unconfirmed = entity.origin === "prediction" && !entity.reviewed;
  const isMergeSource = pendingMergeId === entity.id;
  const isMergeTarget = pendingMergeId !== null && pendingMergeId !== entity.id;

  const typeOptions = types.includes(entity.type) ? types : [entity.type, ...types];

  // Keep the active card visible when cycling with Tab in a long list.
  useEffect(() => {
    if (active) ref.current?.scrollIntoView({ block: "nearest" });
  }, [active]);

  function onCardClick() {
    if (isMergeTarget) {
      mergeEntities(pendingMergeId!, entity.id);
    } else if (selectionSpan) {
      // A span is selected → assign it to this entity (works for any entity, incl. >9).
      addMention(entity.id, selectionSpan);
      setSelectionSpan(null);
      window.getSelection()?.removeAllRanges();
    } else {
      setActiveEntity(entity.id);
    }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation(); // handled here; don't let it fall through to the list's split-on-drop
    setDragOver(false);
    // Clear here too: a split/reassign unmounts the dragged chip, so its own
    // onDragEnd may never fire and would leave the drop-zone stuck on screen.
    setDraggingMention(null);
    const raw = e.dataTransfer.getData("application/json");
    if (!raw) return;
    const data = JSON.parse(raw);
    if (data.kind === "mention" && data.fromId !== entity.id) {
      reassignMention(data.mentionId, data.fromId, entity.id);
    } else if (data.kind === "mention" && data.fromId === entity.id && entity.mentions.length > 1) {
      // Dragged a chip off and released it back over its own card → pull it out
      // into a new entity of its own (the drag-out-to-split gesture). Only when
      // the entity has other mentions; a lone chip has nothing to split from.
      splitMention(entity.id, data.mentionId);
    } else if (data.kind === "entity" && data.entityId !== entity.id) {
      mergeEntities(entity.id, data.entityId); // drop source onto target; target keeps
    }
  }

  return (
    <div
      ref={ref}
      className={
        "ecard" +
        (active ? " active" : "") +
        (unconfirmed ? " unconfirmed" : "") +
        (isMergeTarget ? " merge-target" : "") +
        (dragOver ? " drop-target" : "") +
        // A span is selected → clicking this card adds it here; hint that on hover.
        (selectionSpan ? " pick-target" : "")
      }
      draggable
      onDragStart={(e) =>
        e.dataTransfer.setData("application/json", JSON.stringify({ kind: "entity", entityId: entity.id }))
      }
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={(e) => {
        // Ignore leaves into the card's own children (chips, buttons) to avoid flicker.
        if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragOver(false);
      }}
      onDrop={onDrop}
      onClick={onCardClick}
      onMouseEnter={() => setHoverEntity(entity.id)}
      onMouseLeave={() => setHoverEntity(null)}
    >
      <div className="ecard-head">
        <span className="swatch" style={{ background: color.strong }} />
        {/* Plain position label; assign a selection to this entity by clicking the card. */}
        <span className="keyhint" title="click this card to add the selected text here">
          {index + 1}
        </span>
        <select
          className="type-chip"
          style={{ background: colorForType(entity.type) }}
          value={entity.type}
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => setEntityType(entity.id, e.target.value)}
        >
          {typeOptions.map((t) => (
            <option key={t} value={t} style={{ background: "#fff", color: "#1c2430" }}>
              {t}
            </option>
          ))}
        </select>
        {entity.uid && (
          <span
            className="uid-badge"
            title={`unique id: ${entity.uid} — click to edit`}
            onClick={(e) => {
              e.stopPropagation();
              openUidPrompt(entity.id);
            }}
          >
            {entity.uid}
          </span>
        )}
        <span className="ncount" style={{ fontSize: 11, color: "var(--muted)" }}>
          {entity.mentions.length}×
        </span>
        <div className="ecard-actions" onClick={(e) => e.stopPropagation()}>
          {!entity.uid && (
            <button className="icon-btn" title="set unique identifier" onClick={() => openUidPrompt(entity.id)}>
              id
            </button>
          )}
          <button
            className={"icon-btn" + (entity.reviewed ? " on" : "")}
            title="confirm / unconfirm (r)"
            onClick={() => toggleReviewed(entity.id)}
          >
            ✓
          </button>
          <button
            className="icon-btn"
            title={isMergeSource ? "cancel merge (Esc)" : "merge: click, then click another entity (m)"}
            onClick={() => (isMergeSource ? cancelMerge() : beginMerge(entity.id))}
            style={isMergeSource ? { background: "var(--accent)", color: "#fff" } : undefined}
          >
            ⤵
          </button>
          <button className="icon-btn" title="delete entity" onClick={() => deleteEntity(entity.id)}>
            🗑
          </button>
        </div>
      </div>

      <div className="mentions">
        {entity.mentions.length === 0 && (
          <span style={{ fontSize: 12, color: "var(--muted)" }}>no mentions — select text & press its number</span>
        )}
        {entity.mentions.map((m) => (
          <MentionChip
            key={m.id}
            entityId={entity.id}
            mention={m}
            added={!predictionSpans.has(fragmentsKey(m.fragments))}
          />
        ))}
      </div>
    </div>
  );
}
