import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useStore } from "../store";
import { parseLinkedIds } from "../lib/linkedIds";
import {
  fetchEntityAttributes,
  fetchEntityImage,
  fullEntityUrl,
  type EntityAttributes,
} from "../entityService";

type Load =
  | { state: "loading" }
  | { state: "ok"; attrs: EntityAttributes }
  | { state: "error"; message: string };

/**
 * Knowledge-base card for an entity's linked id, anchored next to the id badge
 * on its entity card. Shows the entity's (Hebrew) attributes, an optional image
 * and a link to the full card on the external site. With several linked ids
 * the first one is shown.
 *
 * Opens from the id badge; closes on Escape, an outside click, or scrolling
 * the entity list (the anchor position goes stale).
 */
export function EntityInfoPopover() {
  const entityId = useStore((s) => s.infoCardEntityId);
  const entity = useStore((s) => s.entities.find((e) => e.id === s.infoCardEntityId));
  const closeInfoCard = useStore((s) => s.closeInfoCard);

  const ids = parseLinkedIds(entity?.uid);
  const id = ids[0];

  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [image, setImage] = useState<string | null>(null);

  // Close if the entity vanished or lost its id while open.
  useEffect(() => {
    if (entityId && !id) closeInfoCard();
  }, [entityId, id, closeInfoCard]);

  useEffect(() => {
    if (!id) return;
    let live = true;
    setLoad({ state: "loading" });
    setImage(null);
    fetchEntityAttributes(id).then(
      (attrs) => live && setLoad({ state: "ok", attrs }),
      (err: unknown) => live && setLoad({ state: "error", message: err instanceof Error ? err.message : String(err) })
    );
    fetchEntityImage(id).then((url) => live && setImage(url));
    return () => {
      live = false;
    };
  }, [id]);

  // Sit to the left of the entity card (over the text column), top-aligned
  // with the badge; fall back to just below the badge when there is no room.
  // Re-run as content loads, since the popover's height changes.
  useLayoutEffect(() => {
    if (!entityId || !ref.current) return;
    const badge = document.querySelector<HTMLElement>(`[data-linked-anchor="${entityId}"]`);
    if (!badge) return;
    const b = badge.getBoundingClientRect();
    const card = (badge.closest(".ecard") as HTMLElement | null)?.getBoundingClientRect() ?? b;
    const m = ref.current.getBoundingClientRect();
    const clampTop = (t: number) => Math.max(8, Math.min(t, window.innerHeight - m.height - 8));
    const clampLeft = (l: number) => Math.max(8, Math.min(l, window.innerWidth - m.width - 8));
    const beside = card.left - m.width - 10;
    if (beside >= 8) setPos({ left: beside, top: clampTop(b.top - 12) });
    else setPos({ left: clampLeft(b.left), top: clampTop(b.bottom + 6) });
  }, [entityId, load, image]);

  useEffect(() => {
    if (!entityId) return;
    function onDown(e: MouseEvent) {
      const t = e.target as HTMLElement;
      if (ref.current?.contains(t)) return;
      // Clicking the badge again toggles; let its own handler decide.
      if (t.closest?.(`[data-linked-anchor="${entityId}"]`)) return;
      closeInfoCard();
    }
    function onScroll(e: Event) {
      if (ref.current?.contains(e.target as Node)) return; // scrolling inside the popover is fine
      closeInfoCard();
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        closeInfoCard();
      }
    }
    document.addEventListener("mousedown", onDown);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", closeInfoCard);
    window.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", closeInfoCard);
      window.removeEventListener("keydown", onKey, true);
    };
  }, [entityId, closeInfoCard]);

  if (!entity || !id) return null;

  const attrs = load.state === "ok" ? load.attrs : null;
  const rows = attrs ? Object.entries(attrs).filter(([key]) => key !== "title") : [];

  return (
    <div
      ref={ref}
      className="info-pop"
      role="dialog"
      aria-label={attrs?.title.value ?? id}
      style={{ left: pos?.left ?? -9999, top: pos?.top ?? -9999, visibility: pos ? "visible" : "hidden" }}
      onClick={(e) => e.stopPropagation()}
      onMouseDown={(e) => e.stopPropagation()}
    >
      <div className="info-head" dir="rtl">
        {image && (
          <img
            className="info-img"
            src={image}
            alt=""
            onError={() => setImage(null)} // broken image → just drop it
          />
        )}
        <div className="info-titles">
          <div className="info-title">
            {attrs ? <bdi>{attrs.title.value}</bdi> : load.state === "loading" ? "טוען…" : id}
          </div>
          <div className="info-id" dir="ltr" title={ids.join(", ")}>
            {id}
            {ids.length > 1 && <span className="info-more"> · 1 of {ids.length} ids</span>}
          </div>
        </div>
        <button className="icon-btn info-close" title="close (Esc)" onClick={closeInfoCard}>
          ×
        </button>
      </div>

      {load.state === "loading" && <div className="info-msg">Loading entity…</div>}
      {load.state === "error" && (
        <div className="info-msg info-err">Couldn't load entity “{id}”: {load.message}</div>
      )}
      {attrs && rows.length > 0 && (
        <dl className="info-attrs" dir="rtl">
          {rows.map(([key, a]) => (
            <div key={key} className="info-row" title={key}>
              <dt>{a?.name ?? key}</dt>
              <dd>{String(a?.value ?? "")}</dd>
            </div>
          ))}
        </dl>
      )}

      <div className="info-foot" dir="rtl">
        <a href={fullEntityUrl(id)} target="_blank" rel="noopener noreferrer">
          לכרטיס המלא ↗
        </a>
      </div>
    </div>
  );
}
