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

  // Scan backwards for @ preceded by whitespace or at start of string
  for (let i = textBefore.length - 1; i >= 0; i--) {
    const ch = textBefore[i];
    if (ch === "@") {
      // @ must be at position 0 or preceded by whitespace
      if (i > 0 && !/\s/.test(textBefore[i - 1])) return null;
      return {
        atIndex: i,
        query: textBefore.substring(i + 1),
      };
    }
    // If we hit a whitespace before finding @, no active mention
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

  const filteredPresets = useMemo(() => {
    if (!mention.isActive) return [];
    const q = mention.query.trim().toLowerCase();
    if (!q) return presets;
    return presets.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        p.description.toLowerCase().includes(q),
    );
  }, [mention.isActive, mention.query, presets]);

  // Reset highlight when filtered list changes
  const prevFilteredLengthRef = useRef(filteredPresets.length);
  if (prevFilteredLengthRef.current !== filteredPresets.length) {
    prevFilteredLengthRef.current = filteredPresets.length;
    if (highlightedIndex >= filteredPresets.length) {
      setHighlightedIndex(0);
    }
  }

  const moveHighlight = useCallback(
    (direction: "up" | "down") => {
      if (filteredPresets.length === 0) return;
      setHighlightedIndex((prev) => {
        if (direction === "down") {
          return (prev + 1) % filteredPresets.length;
        }
        return (prev - 1 + filteredPresets.length) % filteredPresets.length;
      });
    },
    [filteredPresets.length],
  );

  const resetMention = useCallback(() => {
    setHighlightedIndex(0);
  }, []);

  return {
    mention,
    filteredPresets,
    moveHighlight,
    setHighlightedIndex,
    resetMention,
  };
}
