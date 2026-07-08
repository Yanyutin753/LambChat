import type { SlashDropdownItem } from "../components/chat/chatInputSlashCommands";
import type { PersonaPreset } from "../types";
import type { Team } from "../types/team";

interface SlashDropdownState {
  open: boolean;
  items: SlashDropdownItem[];
  highlightIndex: number;
  setHighlightIndex: React.Dispatch<React.SetStateAction<number>>;
  onSelect: (item: SlashDropdownItem) => void;
}

interface MentionDropdownState {
  active: boolean;
  mode: "team" | "persona";
  highlightedIndex: number;
  moveHighlight: (direction: "up" | "down") => void;
  selectHighlighted?: () => void;
  teamItems: Team[];
  personaItems: PersonaPreset[];
  onTeamSelect: (team: Team) => void;
  onPersonaSelect: (preset: PersonaPreset) => void;
  reset: () => void;
}

interface InputNavigationState {
  isLoading: boolean;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  input: string;
  setInput: (value: string | ((prev: string) => string)) => void;
  setCursorPosition: (pos: number | ((prev: number) => number)) => void;
  onSubmit: (e: React.FormEvent) => void;
  onSetStopConfirmOpen: (open: boolean) => void;
  navigateUp: (currentInput: string) => string | null;
  navigateDown: () => string | null;
  historyLength: number;
}

export function useChatInputKeyboard(
  slash: SlashDropdownState,
  mention: MentionDropdownState,
  input: InputNavigationState,
): (e: React.KeyboardEvent) => void {
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (slash.open) {
      if (e.key === "ArrowUp") {
        e.preventDefault();
        const len = slash.items.length;
        slash.setHighlightIndex((prev) => (prev - 1 + len) % len);
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        const len = slash.items.length;
        slash.setHighlightIndex((prev) => (prev + 1) % len);
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        const highlighted = slash.items[slash.highlightIndex];
        if (highlighted) {
          slash.onSelect(highlighted);
        }
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        input.setInput("");
        input.setCursorPosition(0);
        return;
      }
    }

    if (mention.active) {
      if (e.key === "ArrowUp") {
        e.preventDefault();
        mention.moveHighlight("up");
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        mention.moveHighlight("down");
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        if (mention.selectHighlighted) {
          mention.selectHighlighted();
          return;
        }
        if (mention.mode === "team") {
          const highlighted = mention.teamItems[mention.highlightedIndex];
          if (highlighted) mention.onTeamSelect(highlighted);
        } else {
          const highlighted = mention.personaItems[mention.highlightedIndex];
          if (highlighted) mention.onPersonaSelect(highlighted);
        }
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        mention.reset();
        return;
      }
    }

    const newlineModifier = localStorage.getItem("newlineModifier") || "shift";

    if (e.key === "Enter") {
      const needsModifier = newlineModifier === "ctrl" ? e.ctrlKey : e.shiftKey;
      if (needsModifier) return;

      e.preventDefault();
      if (input.isLoading) {
        input.onSetStopConfirmOpen(true);
      } else {
        input.onSubmit(e);
      }
      return;
    }

    const textarea = input.textareaRef.current;
    const atTop =
      textarea?.selectionStart === 0 && textarea?.selectionEnd === 0;
    const value = textarea?.value ?? "";
    const atBottom =
      textarea?.selectionStart === value.length &&
      textarea?.selectionEnd === value.length;

    if (e.key === "ArrowUp" && atTop) {
      e.preventDefault();
      const prev = input.navigateUp(input.input);
      if (prev !== null) {
        input.setInput(prev);
        requestAnimationFrame(() => {
          if (textarea) {
            textarea.selectionStart = textarea.selectionEnd = prev.length;
          }
        });
      }
    } else if (e.key === "ArrowDown" && (atBottom || input.historyLength > 0)) {
      e.preventDefault();
      const next = input.navigateDown();
      if (next !== null) {
        input.setInput(next);
        requestAnimationFrame(() => {
          if (textarea) {
            textarea.selectionStart = textarea.selectionEnd =
              textarea.value.length;
          }
        });
      }
    }
  };

  return handleKeyDown;
}
