import { useEffect, useMemo, useRef } from "react";
import { useStore } from "../store";
import { computeSegments, type SpanInput } from "../lib/segments";
import { cpSlice, normalizeSelection, selectionToSpan } from "../lib/offsets";
import { colorForIndex } from "../colors";

export function TextPanel() {
  const cps = useStore((s) => s.cps);
  const entities = useStore((s) => s.entities);
  const activeEntityId = useStore((s) => s.activeEntityId);
  const hoverEntityId = useStore((s) => s.hoverEntityId);
  const hoverMentionId = useStore((s) => s.hoverMentionId);
  const scrollTo = useStore((s) => s.scrollTo);
  const setSelectionSpan = useStore((s) => s.setSelectionSpan);
  const setActiveEntity = useStore((s) => s.setActiveEntity);
  const setHoverEntity = useStore((s) => s.setHoverEntity);

  const rootRef = useRef<HTMLDivElement>(null);

  // entityId -> { colorIndex, type, active }
  const meta = useMemo(() => {
    const m = new Map<string, { idx: number; active: boolean }>();
    entities.forEach((e, i) => m.set(e.id, { idx: i, active: e.id === activeEntityId }));
    return m;
  }, [entities, activeEntityId]);

  // Mentions flagged "relative" get a distinct look in the text (italic +
  // dotted underline), matching their chips in the entity panel.
  const relativeMentionIds = useMemo(() => {
    const ids = new Set<string>();
    for (const e of entities)
      for (const mn of e.mentions) if (mn.relative) ids.add(mn.id);
    return ids;
  }, [entities]);

  const segments = useMemo(() => {
    const spans: SpanInput[] = [];
    for (const e of entities) {
      for (const mn of e.mentions) {
        for (const f of mn.fragments) {
          spans.push({ entityId: e.id, mentionId: mn.id, start: f.start, end: f.end });
        }
      }
    }
    return computeSegments(cps.length, spans);
  }, [entities, cps.length]);

  // Scroll/flash a requested span (clicked from an entity chip).
  useEffect(() => {
    if (!scrollTo || !rootRef.current) return;
    const el = rootRef.current.querySelector<HTMLElement>(`[data-start="${scrollTo.start}"]`);
    if (el) {
      el.scrollIntoView({ block: "center", behavior: "smooth" });
      el.classList.remove("flash");
      void el.offsetWidth; // restart animation
      el.classList.add("flash");
    }
  }, [scrollTo]);

  function onMouseUp() {
    if (!rootRef.current) return;
    const raw = selectionToSpan(rootRef.current);
    if (!raw) {
      setSelectionSpan(null);
      return;
    }
    const span = normalizeSelection(cps, raw.start, raw.end);
    setSelectionSpan(span);
  }

  function onSegmentClick(entityIds: string[]) {
    // Plain click (no selection) on a covered span -> activate its top entity.
    const sel = window.getSelection();
    if (sel && !sel.isCollapsed) return;
    if (entityIds.length > 0) setActiveEntity(entityIds[entityIds.length - 1]);
  }

  return (
    <div className="text-scroll">
      {/* dir="auto" → the browser's bidi algorithm picks LTR/RTL per document
          (Hebrew/Arabic render RTL; embedded English & numbers stay correct). */}
      <div className="doc-text" dir="auto" ref={rootRef} onMouseUp={onMouseUp}>
        {segments.map((seg) => {
          const text = cpSlice(cps, seg.start, seg.end);
          if (seg.entityIds.length === 0) {
            return (
              <span key={seg.start} data-start={seg.start} data-end={seg.end}>
                {text}
              </span>
            );
          }
          // primary = active entity if it covers here, else top-most (last) covering
          const activeHere = seg.entityIds.find((id) => meta.get(id)?.active);
          const primaryId = activeHere ?? seg.entityIds[seg.entityIds.length - 1];
          const primary = colorForIndex(meta.get(primaryId)!.idx);

          // stacked underline bars (one per covering entity) over the tint fill;
          // the tint must be the final layer of the `background` shorthand.
          const tint = activeHere ? primary.bgActive : primary.bg;
          const bars = seg.entityIds
            .map((id, k) => {
              const c = colorForIndex(meta.get(id)!.idx).strong;
              return `linear-gradient(${c}, ${c}) 0 calc(100% - ${k * 3}px)/100% 2px no-repeat`;
            })
            .join(", ");

          // A specific mention hover (hovering its chip) narrows the highlight to
          // just that mention, even though the chip sits inside its entity card —
          // mouseenter doesn't re-fire on the card when moving onto a child, so
          // hoverEntityId is still set and would otherwise light up every mention.
          const isHover = hoverMentionId
            ? seg.mentionIds.includes(hoverMentionId)
            : seg.entityIds.includes(hoverEntityId ?? "");

          const isRelative = seg.mentionIds.some((id) => relativeMentionIds.has(id));

          return (
            <span
              key={seg.start}
              className={"seg covered" + (isRelative ? " relative" : "")}
              data-start={seg.start}
              data-end={seg.end}
              style={{
                background: `${bars}, ${tint}`,
                paddingBottom: `${seg.entityIds.length * 3}px`,
                boxShadow: isHover ? "inset 0 0 0 1.5px rgba(37,99,235,0.7)" : undefined,
              }}
              onClick={() => onSegmentClick(seg.entityIds)}
              onMouseEnter={() => setHoverEntity(primaryId)}
              onMouseLeave={() => setHoverEntity(null)}
              title={seg.entityIds.map((id) => entities.find((e) => e.id === id)?.type).join(" / ")}
            >
              {text}
            </span>
          );
        })}
      </div>
    </div>
  );
}
