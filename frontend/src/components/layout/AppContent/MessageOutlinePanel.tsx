import { lazy, Suspense } from "react";
import type { MessageOutlineItem } from "./messageOutline";

// @xyflow/react (~380KB) only powers this outline graph; load it on demand
// instead of shipping it inside the first-paint shell.
const MessageOutlineFlow = lazy(() => import("./MessageOutlineFlow"));

interface MessageOutlinePanelProps {
  items: MessageOutlineItem[];
  activeId: string | null;
  onNavigate: (anchorId: string, messageIndex: number) => void;
  personaAvatar?: string | null;
}

export function MessageOutlinePanel(props: MessageOutlinePanelProps) {
  if (props.items.length === 0) return null;

  return (
    <Suspense fallback={null}>
      <MessageOutlineFlow {...props} />
    </Suspense>
  );
}
