import { useEffect, useState } from "react";
import { memoryApi, type MemoryItem } from "../../../services/api/memory";

/** List records may contain only the excerpt of content stored separately. */
export function useMemoryContent(memory?: MemoryItem | null) {
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{
    memory: MemoryItem;
    attempt: number;
    full?: MemoryItem;
    error?: boolean;
  } | null>(null);
  const current =
    result?.memory === memory && result?.attempt === attempt ? result : null;

  useEffect(() => {
    if (!memory?.has_full_content) return;
    let cancelled = false;
    memoryApi.get(memory.memory_id).then(
      (full) => {
        if (!cancelled) setResult({ memory, attempt, full });
      },
      () => {
        if (!cancelled) setResult({ memory, attempt, error: true });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [memory, attempt]);

  return {
    full: memory?.has_full_content ? current?.full : memory,
    loading: !!memory?.has_full_content && !current,
    error: !!current?.error,
    retry: () => setAttempt((value) => value + 1),
  };
}
