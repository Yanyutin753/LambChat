/**
 * Mobile touch drag-to-project hook
 */

import { useState, useCallback, useRef } from "react";
import { useTranslation } from "react-i18next";
import type { BackendSession } from "../services/api";

interface TouchDragState {
  draggingSessionId: string | null;
  touchDropTarget: string | null;
  dragIndicatorPos: { x: number; y: number } | null;
  dragIndicatorTitle: string;
}

interface UseTouchDragReturn extends TouchDragState {
  handleDragStartTouch: (
    sessionId: string,
    clientX: number,
    clientY: number,
  ) => void;
}

export function useTouchDrag(
  sessions: BackendSession[],
  onDrop: (sessionId: string, projectId: string) => void,
): UseTouchDragReturn {
  const { t } = useTranslation();
  const [draggingSessionId, setDraggingSessionId] = useState<string | null>(
    null,
  );
  const [touchDropTarget, setTouchDropTarget] = useState<string | null>(null);
  const [dragIndicatorPos, setDragIndicatorPos] = useState<{
    x: number;
    y: number;
  } | null>(null);
  const [dragIndicatorTitle, setDragIndicatorTitle] = useState<string>("");

  const touchDragRef = useRef<{
    sessionId: string;
    clientX: number;
    clientY: number;
  } | null>(null);
  const touchDropTargetRef = useRef<string | null>(null);
  const onDropRef = useRef(onDrop);
  onDropRef.current = onDrop;
  const sessionsRef = useRef(sessions);
  sessionsRef.current = sessions;

  const handleDragStartTouch = useCallback(
    (sessionId: string, clientX: number, clientY: number) => {
      setDraggingSessionId(sessionId);
      touchDragRef.current = { sessionId, clientX, clientY };
      touchDropTargetRef.current = null;
      setDragIndicatorPos({ x: clientX, y: clientY });

      // Get session title for the drag indicator
      const s = sessionsRef.current.find((s) => s.id === sessionId);
      if (s) {
        const meta = s.metadata as Record<string, unknown>;
        const title = s.name || (meta?.title as string) || t("sidebar.newChat");
        setDragIndicatorTitle(title);
      }

      const handleDocumentTouchMove = (e: TouchEvent) => {
        if (!touchDragRef.current || e.touches.length === 0) return;
        e.preventDefault();
        const touch = e.touches[0];
        touchDragRef.current.clientX = touch.clientX;
        touchDragRef.current.clientY = touch.clientY;
        setDragIndicatorPos({ x: touch.clientX, y: touch.clientY });
        const el = document.elementFromPoint(touch.clientX, touch.clientY);
        if (el) {
          const projectHeader = el.closest("[data-project-drop]");
          if (projectHeader) {
            const projectId = projectHeader.getAttribute("data-project-id");
            touchDropTargetRef.current = projectId;
            setTouchDropTarget(projectId);
          } else {
            touchDropTargetRef.current = null;
            setTouchDropTarget(null);
          }
        }
      };
      const handleDocumentTouchEnd = () => {
        const targetId = touchDropTargetRef.current;
        if (targetId && touchDragRef.current) {
          onDropRef.current(touchDragRef.current.sessionId, targetId);
        }
        setDraggingSessionId(null);
        setTouchDropTarget(null);
        setDragIndicatorPos(null);
        touchDragRef.current = null;
        touchDropTargetRef.current = null;
        document.removeEventListener("touchmove", handleDocumentTouchMove);
        document.removeEventListener("touchend", handleDocumentTouchEnd);
      };
      document.addEventListener("touchmove", handleDocumentTouchMove, {
        passive: false,
      });
      document.addEventListener("touchend", handleDocumentTouchEnd);
    },
    [t],
  );

  return {
    draggingSessionId,
    touchDropTarget,
    dragIndicatorPos,
    dragIndicatorTitle,
    handleDragStartTouch,
  };
}
