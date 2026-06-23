import { useEffect } from "react";
import { useStore } from "../store";

function isTypingTarget(el: EventTarget | null): boolean {
  const node = el as HTMLElement | null;
  if (!node) return false;
  const tag = node.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || node.isContentEditable;
}

function clearNativeSelection() {
  window.getSelection()?.removeAllRanges();
}

export function useKeyboard(toggleHelp: () => void) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (isTypingTarget(e.target)) return;
      const s = useStore.getState();
      const span = s.selectionSpan;
      const types = s.config?.types ?? ["PER", "LOC", "ORG", "TIME"];

      // help
      if (e.key === "?") {
        e.preventDefault();
        toggleHelp();
        return;
      }

      // undo / redo
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        if (e.shiftKey) s.redo();
        else s.undo();
        return;
      }
      if (e.ctrlKey || e.metaKey) return; // leave other ctrl combos to the browser

      // entity type assignment / creation
      const typeKey: Record<string, string> = { p: "PER", l: "LOC", o: "ORG", t: "TIME" };
      const mapped = typeKey[e.key.toLowerCase()];
      if (mapped && types.includes(mapped)) {
        e.preventDefault();
        if (span) {
          s.createEntity(mapped, span);
          s.setSelectionSpan(null);
          clearNativeSelection();
        } else if (s.activeEntityId) {
          s.setEntityType(s.activeEntityId, mapped);
        }
        return;
      }

      // digits -> entity N
      if (/^[1-9]$/.test(e.key)) {
        const idx = Number(e.key) - 1;
        const target = s.entities[idx];
        if (target) {
          e.preventDefault();
          if (span) {
            s.addMention(target.id, span);
            s.setSelectionSpan(null);
            clearNativeSelection();
          } else {
            s.setActiveEntity(target.id);
          }
        }
        return;
      }

      switch (e.key) {
        case "a":
          if (span) {
            e.preventDefault();
            s.addToActive(span);
            s.setSelectionSpan(null);
            clearNativeSelection();
          }
          return;
        case "A":
          e.preventDefault();
          s.acceptAll();
          return;
        case "n":
          e.preventDefault();
          s.newEmptyEntity();
          return;
        case "r":
          if (s.activeEntityId) {
            e.preventDefault();
            s.toggleReviewed(s.activeEntityId);
          }
          return;
        case "m":
          if (s.activeEntityId) {
            e.preventDefault();
            if (s.pendingMergeId === s.activeEntityId) s.cancelMerge();
            else s.beginMerge(s.activeEntityId);
          }
          return;
        case "s": {
          if (s.hoverMentionId) {
            const owner = s.entities.find((en) => en.mentions.some((m) => m.id === s.hoverMentionId));
            if (owner) {
              e.preventDefault();
              s.splitMention(owner.id, s.hoverMentionId);
            }
          }
          return;
        }
        case "Delete":
        case "Backspace": {
          if (s.hoverMentionId) {
            const owner = s.entities.find((en) => en.mentions.some((m) => m.id === s.hoverMentionId));
            if (owner) {
              e.preventDefault();
              s.removeMention(owner.id, s.hoverMentionId);
            }
          }
          return;
        }
        case "Tab":
          e.preventDefault();
          s.cycleActive(e.shiftKey ? -1 : 1);
          return;
        case "Escape":
          s.cancelMerge();
          s.setSelectionSpan(null);
          clearNativeSelection();
          return;
        case "d":
          e.preventDefault();
          s.markDone();
          return;
        case "ArrowRight":
          s.next();
          return;
        case "ArrowLeft":
          s.prev();
          return;
      }
    }

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggleHelp]);
}
