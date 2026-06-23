import { useStore } from "../store";
import { cpSlice } from "../lib/offsets";
import type { Mention } from "../types";

interface Props {
  entityId: string;
  mention: Mention;
  added: boolean; // not present in the original prediction (a human addition)
}

export function MentionChip({ entityId, mention, added }: Props) {
  const cps = useStore((s) => s.cps);
  const removeMention = useStore((s) => s.removeMention);
  const requestScrollTo = useStore((s) => s.requestScrollTo);
  const setHoverMention = useStore((s) => s.setHoverMention);
  const hoverMentionId = useStore((s) => s.hoverMentionId);

  const surface = cpSlice(cps, mention.start, mention.end);

  return (
    <span
      className={"chip" + (hoverMentionId === mention.id ? " hover" : "")}
      draggable
      onDragStart={(e) => {
        e.stopPropagation();
        e.dataTransfer.setData(
          "application/json",
          JSON.stringify({ kind: "mention", mentionId: mention.id, fromId: entityId })
        );
        e.dataTransfer.effectAllowed = "move";
      }}
      onClick={() => requestScrollTo(mention.start)}
      onMouseEnter={() => setHoverMention(mention.id)}
      onMouseLeave={() => setHoverMention(null)}
      title={`[${mention.start}, ${mention.end})  — click to locate, drag to reassign`}
    >
      {added && <span className="added" title="added vs. prediction">+</span>}
      {/* <bdi> isolates RTL surface text so it doesn't reorder the +/× controls */}
      <bdi>{surface || "∅"}</bdi>
      <span
        className="x"
        title="remove mention"
        onClick={(e) => {
          e.stopPropagation();
          removeMention(entityId, mention.id);
        }}
      >
        ×
      </span>
    </span>
  );
}
