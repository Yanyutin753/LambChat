import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
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
  const navigate = useNavigate();
  const { pathname, search, hash } = useLocation();
  useEffect(() => {
    if (
      sessionId &&
      context?.sessionId === sessionId &&
      context.assistant &&
      pathname === `/chat/${encodeURIComponent(sessionId)}`
    ) {
      navigate(
        `/assistants/${encodeURIComponent(
          context.assistant.id,
        )}/chat/${encodeURIComponent(sessionId)}${search}${hash}`,
        { replace: true },
      );
    }
  }, [sessionId, context, pathname, search, hash, navigate]);
  return {
    assistant:
      context && context.sessionId === sessionId ? context.assistant : null,
    onAssistantResolved,
  };
}
