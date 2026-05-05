import { useCallback, useMemo, useRef, useState } from "react";
import type { PersonaPreset } from "../types";

export interface MentionState {
  isActive: boolean;
  query: string;
  atIndex: number;
  highlightedIndex: number;
}

function detectMention(
  input: string,
  cursorPosition: number,
): { atIndex: number; query: string } | null {
  if (cursorPosition <= 0) return null;

  const textBefore = input.substring(0, cursorPosition);

  for (let i = textBefore.length - 1; i >= 0; i--) {
    const ch = textBefore[i];
    if (ch === "@") {
      if (i > 0 && !/\s/.test(textBefore[i - 1])) return null;
      return {
        atIndex: i,
        query: textBefore.substring(i + 1),
      };
    }
    if (/\s/.test(ch)) return null;
  }

  return null;
}

export function useMentionState(
  input: string,
  cursorPosition: number,
  presets: PersonaPreset[],
) {
  const [highlightedIndex, setHighlightedIndex] = useState(0);
  const resultCountRef = useRef(0);

  const mention: MentionState = useMemo(() => {
    if (presets.length === 0) {
      return { isActive: false, query: "", atIndex: -1, highlightedIndex: 0 };
    }

    const detected = detectMention(input, cursorPosition);
    if (!detected) {
      return { isActive: false, query: "", atIndex: -1, highlightedIndex: 0 };
    }

    return {
      isActive: true,
      query: detected.query,
      atIndex: detected.atIndex,
      highlightedIndex,
    };
  }, [input, cursorPosition, presets.length, highlightedIndex]);

  const moveHighlight = useCallback((direction: "up" | "down") => {
    const len = resultCountRef.current;
    if (len === 0) return;
    setHighlightedIndex((prev) => {
      if (direction === "down") {
        return (prev + 1) % len;
      }
      return (prev - 1 + len) % len;
    });
  }, []);

  const resetMention = useCallback(() => {
    setHighlightedIndex(0);
  }, []);

  const setResultCount = useCallback((count: number) => {
    resultCountRef.current = count;
    setHighlightedIndex((prev) => (prev >= count ? 0 : prev));
  }, []);

  return {
    mention,
    moveHighlight,
    setHighlightedIndex,
    setResultCount,
    resetMention,
  };
}
