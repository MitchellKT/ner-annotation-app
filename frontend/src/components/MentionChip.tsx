import { Fragment } from "react";
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
  const removeFragment = useStore((s) => s.removeFragment);
  const addFragment = useStore((s) => s.addFragment);
  const requestScrollTo = useStore((s) => s.requestScrollTo);
  const setHoverMention = useStore((s) => s.setHoverMention);
  const hoverMentionId = useStore((s) => s.hoverMentionId);
  const selectionSpan = useStore((s) => s.selectionSpan);
  const setSelectionSpan = useStore((s) => s.setSelectionSpan);
  const setDraggingMention = useStore((s) => s.setDraggingMention);

  const discontinuous = mention.fragments.length > 1;

  function onChipClick(e: React.MouseEvent) {
    if (selectionSpan) {
      // A span is selected → attach it to THIS mention as an extra fragment
      // (non-continuous mention). Don't bubble: the card click would add it
      // as a separate mention instead.
      e.stopPropagation();
      addFragment(entityId, mention.id, selectionSpan);
      setSelectionSpan(null);
      window.getSelection()?.removeAllRanges();
      return;
    }
    requestScrollTo(mention.fragments[0].start);
  }

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
        setDraggingMention({ mentionId: mention.id, fromId: entityId });
      }}
      onDragEnd={() => setDraggingMention(null)}
      onClick={onChipClick}
      onMouseEnter={() => setHoverMention(mention.id)}
      onMouseLeave={() => setHoverMention(null)}
      title={
        mention.fragments.map((f) => `[${f.start}, ${f.end})`).join(" + ") +
        " — click to locate (with text selected: add as fragment), drag onto another entity to reassign, drag onto empty space to split into a new entity"
      }
    >
      {added && <span className="added" title="added vs. prediction">+</span>}
      {mention.fragments.map((f, i) => {
        const surface = cpSlice(cps, f.start, f.end);
        return (
          <Fragment key={`${f.start}:${f.end}`}>
            {i > 0 && <span className="frag-gap" title="non-continuous mention">‥</span>}
            {/* <bdi> isolates RTL surface text so it doesn't reorder controls */}
            <bdi>{surface || "∅"}</bdi>
            {discontinuous && (
              <span
                className="x"
                title="remove this fragment"
                onClick={(e) => {
                  e.stopPropagation();
                  removeFragment(entityId, mention.id, i);
                }}
              >
                ×
              </span>
            )}
          </Fragment>
        );
      })}
      {!discontinuous && (
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
      )}
    </span>
  );
}
