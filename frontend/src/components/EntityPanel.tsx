import { useMemo } from "react";
import { useStore } from "../store";
import { EntityCard } from "./EntityCard";

export function EntityPanel() {
  const entities = useStore((s) => s.entities);
  const prediction = useStore((s) => s.prediction);
  const types = useStore((s) => s.config?.types ?? ["PER", "LOC", "ORG", "TIME"]);
  const acceptAll = useStore((s) => s.acceptAll);
  const newEmptyEntity = useStore((s) => s.newEmptyEntity);
  const revertToPrediction = useStore((s) => s.revertToPrediction);
  const hasPrediction = prediction.length > 0;

  // Digit keys 1-9 create an entity of the matching type; cap the hint at the
  // number of configured types (and at 9, the highest reachable digit).
  const maxKey = Math.min(types.length, 9);

  const predictionSpans = useMemo(() => {
    const s = new Set<string>();
    for (const e of prediction) for (const m of e.mentions) s.add(`${m.start}:${m.end}`);
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

      <div className="entity-list">
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
