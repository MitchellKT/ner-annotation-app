import { useMemo } from "react";
import { useStore } from "../store";
import { EntityCard } from "./EntityCard";
import { fragmentsKey, wireFragments } from "../lib/mentions";

export function EntityPanel() {
  const entities = useStore((s) => s.entities);
  const prediction = useStore((s) => s.prediction);
  const types = useStore((s) => s.config?.types ?? ["PER", "LOC", "ORG", "TIME"]);
  const acceptAll = useStore((s) => s.acceptAll);
  const newEmptyEntity = useStore((s) => s.newEmptyEntity);
  const revertToPrediction = useStore((s) => s.revertToPrediction);
  const draggingMention = useStore((s) => s.draggingMention);
  const splitMention = useStore((s) => s.splitMention);
  const setDraggingMention = useStore((s) => s.setDraggingMention);
  const hasPrediction = prediction.length > 0;

  function onListDrop(e: React.DragEvent) {
    e.preventDefault();
    const raw = e.dataTransfer.getData("application/json");
    setDraggingMention(null);
    if (!raw) return;
    const data = JSON.parse(raw);
    // A mention dropped anywhere that isn't another entity card (which stops
    // propagation itself) — pull it out into a brand-new entity. A lone mention
    // has nothing to split from, so ignore it.
    if (data.kind === "mention") {
      const src = entities.find((en) => en.id === data.fromId);
      if (src && src.mentions.length > 1) splitMention(data.fromId, data.mentionId);
    }
  }

  // Splitting only makes sense when the dragged mention's entity has siblings;
  // otherwise the "drop to split" hint would recreate the same entity.
  const canSplitDragged =
    !!draggingMention &&
    (entities.find((en) => en.id === draggingMention.fromId)?.mentions.length ?? 0) > 1;

  // Digit keys 1-9 create an entity of the matching type; cap the hint at the
  // number of configured types (and at 9, the highest reachable digit).
  const maxKey = Math.min(types.length, 9);

  const predictionSpans = useMemo(() => {
    const s = new Set<string>();
    for (const e of prediction) for (const m of e.mentions) s.add(fragmentsKey(wireFragments(m)));
    return s;
  }, [prediction]);

  const allReviewed = entities.length > 0 && entities.every((e) => e.reviewed);

  return (
    <>
      <div className="entity-tools">
        <strong style={{ fontSize: 13 }}>Entities</strong>
        <span style={{ fontSize: 12, color: "var(--muted)" }}>{entities.length}</span>
        <span className="spacer" style={{ flex: 1 }} />
        <button onClick={newEmptyEntity} title="new empty entity (n)">+ New</button>
        {hasPrediction && (
          <button onClick={acceptAll} disabled={allReviewed} title="confirm every entity (A)">
            Accept all
          </button>
        )}
        {hasPrediction && (
          <button onClick={revertToPrediction} title="discard edits, restore the model prediction">
            ⟲ Revert
          </button>
        )}
      </div>

      <div className="entity-list" onDragOver={(e) => e.preventDefault()} onDrop={onListDrop}>
        {canSplitDragged && (
          <div className="split-dropzone">Drop here to split into a new entity</div>
        )}
        {entities.length === 0 && (
          <div className="entity-empty">
            No entities yet.
            <br />
            Select text and press{" "}
            {maxKey > 1 ? (
              <>
                <kbd>1</kbd>–<kbd>{maxKey}</kbd>
              </>
            ) : (
              <kbd>1</kbd>
            )}{" "}
            (the entity type) to create one.
          </div>
        )}
        {entities.map((e, i) => (
          <EntityCard key={e.id} entity={e} index={i} predictionSpans={predictionSpans} />
        ))}
      </div>
    </>
  );
}
