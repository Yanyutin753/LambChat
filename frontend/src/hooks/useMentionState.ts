import { useCallback, useEffect, useMemo, useRef, useState } from "react";

export interface MentionState {
  isActive: boolean;
  query: string;
  atIndex: number;
  highlightedIndex: number;
}

interface MentionMatch {
  atIndex: number;
  query: string;
}

interface DismissedMention {
  input: string;
  atIndex: number;
}

export function findMentionMatch(
  input: string,
  cursorPosition: number,
): MentionMatch | null {
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

export function getMentionState({
  input,
  cursorPosition,
  enabled,
  highlightedIndex,
  dismissedMention,
}: {
  input: string;
  cursorPosition: number;
  enabled: boolean;
  highlightedIndex: number;
  dismissedMention: DismissedMention | null;
}): MentionState {
  if (!enabled) {
    return { isActive: false, query: "", atIndex: -1, highlightedIndex: 0 };
  }

  const match = findMentionMatch(input, cursorPosition);
  if (!match) {
    return { isActive: false, query: "", atIndex: -1, highlightedIndex: 0 };
  }

  if (
    dismissedMention &&
    dismissedMention.input === input &&
    dismissedMention.atIndex === match.atIndex
  ) {
    return { isActive: false, query: "", atIndex: -1, highlightedIndex: 0 };
  }

  return {
    isActive: true,
    query: match.query,
    atIndex: match.atIndex,
    highlightedIndex,
  };
}

export function useMentionState(
  input: string,
  cursorPosition: number,
  enabled: boolean,
) {
  const [highlightedIndex, setHighlightedIndex] = useState(0);
  const [dismissedMention, setDismissedMention] =
    useState<DismissedMention | null>(null);
  const resultCountRef = useRef(0);

  useEffect(() => {
    if (!findMentionMatch(input, cursorPosition)) {
      setDismissedMention(null);
    }
  }, [input, cursorPosition]);

  const mention: MentionState = useMemo(
    () =>
      getMentionState({
        input,
        cursorPosition,
        enabled,
        highlightedIndex,
        dismissedMention,
      }),
    [input, cursorPosition, enabled, highlightedIndex, dismissedMention],
  );

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

  const dismissMention = useCallback(() => {
    const match = findMentionMatch(input, cursorPosition);
    if (match) {
      setDismissedMention({ input, atIndex: match.atIndex });
    }
    setHighlightedIndex(0);
  }, [input, cursorPosition]);

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
    dismissMention,
  };
}
