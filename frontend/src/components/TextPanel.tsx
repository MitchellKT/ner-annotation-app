import { useEffect, useMemo, useRef } from "react";
import { useStore } from "../store";
import { computeSegments, type Segment, type SpanInput } from "../lib/segments";
import { cpSlice, normalizeSelection, selectionToSpan } from "../lib/offsets";
import { colorForIndex } from "../colors";
import { MentionMenu } from "./MentionMenu";

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
  const openMentionMenu = useStore((s) => s.openMentionMenu);
  const closeMentionMenu = useStore((s) => s.closeMentionMenu);

  const rootRef = useRef<HTMLDivElement>(null);

  // entityId -> { colorIndex, type, active }
  const meta = useMemo(() => {
    const m = new Map<string, { idx: number; active: boolean }>();
    entities.forEach((e, i) => m.set(e.id, { idx: i, active: e.id === activeEntityId }));
    return m;
  }, [entities, activeEntityId]);

  // Mentions flagged "relative" get a distinct look in the text (a diagonal
  // hatch over the highlight box), matching their chips in the entity panel.
  const relativeMentionIds = useMemo(() => {
    const ids = new Set<string>();
    for (const e of entities)
      for (const mn of e.mentions) if (mn.relative) ids.add(mn.id);
    return ids;
  }, [entities]);

  // mentionId -> its owning entity, size (total fragment length) and stacking
  // order. Used to pick a click target when several mentions cover one spot:
  // the shortest mention wins, so one strictly contained in another (e.g.
  // "Obama" inside "Barack Obama") stays reachable on its own text.
  const mentionMeta = useMemo(() => {
    const m = new Map<string, { entityId: string; size: number; order: number }>();
    let order = 0;
    for (const e of entities) {
      for (const mn of e.mentions) {
        const size = mn.fragments.reduce((a, f) => a + (f.end - f.start), 0);
        m.set(mn.id, { entityId: e.id, size, order: order++ });
      }
    }
    return m;
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
    // Starting a fresh selection dismisses any open mention bar.
    closeMentionMenu();
    const span = normalizeSelection(cps, raw.start, raw.end);
    setSelectionSpan(span);
  }

  function onSegmentClick(seg: Segment) {
    // Plain click (no selection) on a covered span -> activate the targeted
    // entity and pop up that mention's action bar right above the text.
    const sel = window.getSelection();
    if (sel && !sel.isCollapsed) return;
    // Among the mentions covering this spot, target the shortest one, so a
    // mention strictly contained in another is reachable on its own text
    // instead of always yielding to the longer one on top. Ties prefer the
    // active entity, then the top-most (last) mention.
    const candidates: { mid: string; entityId: string; size: number; order: number }[] = [];
    for (const mid of seg.mentionIds) {
      const info = mentionMeta.get(mid);
      if (info) candidates.push({ mid, ...info });
    }
    if (candidates.length === 0) return;
    candidates.sort(
      (a, b) =>
        a.size - b.size ||
        Number(b.entityId === activeEntityId) - Number(a.entityId === activeEntityId) ||
        b.order - a.order
    );
    const target = candidates[0];
    setActiveEntity(target.entityId);
    openMentionMenu({ entityId: target.entityId, mentionId: target.mid, anchorStart: seg.start });
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

          // A relative mention (refers via a relation, e.g. "father of Abraham")
          // is marked by a diagonal hatch over its fill — a layer that sits above
          // the tint but below the underline bars.
          const isRelative = seg.mentionIds.some((id) => relativeMentionIds.has(id));
          const hatch =
            "repeating-linear-gradient(-45deg, rgba(30,41,59,0.16) 0, rgba(30,41,59,0.16) 3px, transparent 3px, transparent 7px)";
          const fill = isRelative ? `${hatch}, ${tint}` : tint;

          // A specific mention hover (hovering its chip) narrows the highlight to
          // just that mention, even though the chip sits inside its entity card —
          // mouseenter doesn't re-fire on the card when moving onto a child, so
          // hoverEntityId is still set and would otherwise light up every mention.
          const isHover = hoverMentionId
            ? seg.mentionIds.includes(hoverMentionId)
            : seg.entityIds.includes(hoverEntityId ?? "");

          return (
            <span
              key={seg.start}
              className={"seg covered" + (isRelative ? " relative" : "")}
              data-start={seg.start}
              data-end={seg.end}
              style={{
                background: `${bars}, ${fill}`,
                paddingBottom: `${seg.entityIds.length * 3}px`,
                boxShadow: isHover ? "inset 0 0 0 1.5px rgba(37,99,235,0.7)" : undefined,
              }}
              onClick={() => onSegmentClick(seg)}
              onMouseEnter={() => setHoverEntity(primaryId)}
              onMouseLeave={() => setHoverEntity(null)}
              title={seg.entityIds.map((id) => entities.find((e) => e.id === id)?.type).join(" / ")}
            >
              {text}
            </span>
          );
        })}
      </div>
      <MentionMenu />
    </div>
  );
}
