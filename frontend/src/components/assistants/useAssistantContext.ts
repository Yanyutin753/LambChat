import { useCallback, useState } from "react";
import type { Assistant } from "../../types/assistant";

export function useAssistantContext(sessionId: string | null | undefined) {
  const [context, setContext] = useState<{
    sessionId: string;
    assistant: Assistant | null;
  } | null>(null);
  const onAssistantResolved = useCallback(
    (resolvedSessionId: string, assistant: Assistant | null) =>
      setContext({ sessionId: resolvedSessionId, assistant }),
    [],
  );
  return {
    assistant:
      context && context.sessionId === sessionId ? context.assistant : null,
    onAssistantResolved,
  };
}
