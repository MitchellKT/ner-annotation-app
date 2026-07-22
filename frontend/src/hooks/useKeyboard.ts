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
      if (s.phase !== "annotate") return; // shortcuts only while annotating
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

      // digits 1-9 -> entity type N: create a new entity of that type from the
      // selection, or (with nothing selected) retype the active entity.
      if (/^[1-9]$/.test(e.key)) {
        const type = types[Number(e.key) - 1];
        if (type) {
          e.preventDefault();
          if (span) {
            s.createEntity(type, span);
            s.setSelectionSpan(null);
            clearNativeSelection();
          } else if (s.activeEntityId) {
            s.setEntityType(s.activeEntityId, type);
          }
        }
        return;
      }

      switch (e.key) {
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
        case "t":
          if (s.activeEntityId) {
            e.preventDefault();
            s.openTagPrompt(s.activeEntityId);
          }
          return;
        case "c":
          // Toggle the shared comment thread; opening focuses its composer.
          e.preventDefault();
          s.setCommentsOpen(!s.commentsOpen);
          return;
        case "m":
          if (s.activeEntityId) {
            e.preventDefault();
            if (s.pendingMergeId === s.activeEntityId) s.cancelMerge();
            else s.beginMerge(s.activeEntityId);
          }
          return;
        case "x": {
          // Extend: attach the selection as an extra fragment of a mention,
          // making it non-continuous. Targets the hovered mention if any,
          // else the active entity's last mention.
          if (!span) return;
          const target = s.hoverMentionId
            ? s.entities.find((en) => en.mentions.some((m) => m.id === s.hoverMentionId))
            : s.entities.find((en) => en.id === s.activeEntityId);
          if (!target || target.mentions.length === 0) return;
          const mention = s.hoverMentionId
            ? target.mentions.find((m) => m.id === s.hoverMentionId)!
            : target.mentions[target.mentions.length - 1];
          e.preventDefault();
          s.addFragment(target.id, mention.id, span);
          s.setSelectionSpan(null);
          clearNativeSelection();
          return;
        }
        case "R": {
          // Toggle "relative" on a mention: the hovered one, else the active
          // entity's last mention (mirrors `x`). No selection needed.
          const owner = s.hoverMentionId
            ? s.entities.find((en) => en.mentions.some((m) => m.id === s.hoverMentionId))
            : s.entities.find((en) => en.id === s.activeEntityId);
          if (!owner || owner.mentions.length === 0) return;
          const mention = s.hoverMentionId
            ? owner.mentions.find((m) => m.id === s.hoverMentionId)!
            : owner.mentions[owner.mentions.length - 1];
          e.preventDefault();
          s.toggleMentionRelative(owner.id, mention.id);
          return;
        }
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
          s.closeMentionMenu();
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
