import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Lightbulb, MessageCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  buildSelectionActionPrompt,
  dispatchSelectionActionPrompt,
  getSelectionPopoverPosition,
  storePendingSelectionActionPrompt,
  type SelectionAction,
} from "./selectionActionPopoverUtils";

const MENU_WIDTH = 142;
const MENU_HEIGHT = 34;

interface PopoverState {
  selectedText: string;
  left: number;
  top: number;
}

function getNodeElement(node: Node | null): Element | null {
  if (!node) return null;
  return node.nodeType === Node.ELEMENT_NODE
    ? (node as Element)
    : node.parentElement;
}

function isSelectionInEditableArea(selection: Selection): boolean {
  const anchorElement = getNodeElement(selection.anchorNode);
  const focusElement = getNodeElement(selection.focusNode);
  return [anchorElement, focusElement].some((element) => {
    if (!element) return false;
    return !!element.closest(
      'input, textarea, select, button, [contenteditable="true"], [data-selection-action-popover]',
    );
  });
}

function getVisibleSelectionRect(range: Range): DOMRect | null {
  const rect = range.getBoundingClientRect();
  if (rect.width > 0 && rect.height > 0) return rect;

  const firstRect = Array.from(range.getClientRects()).find(
    (clientRect) => clientRect.width > 0 && clientRect.height > 0,
  );
  return firstRect ?? null;
}

export function SelectionActionPopover() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const [popover, setPopover] = useState<PopoverState | null>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const latestTextRef = useRef("");

  const hidePopover = useCallback(() => {
    setPopover(null);
    latestTextRef.current = "";
  }, []);

  const updateFromSelection = useCallback(() => {
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0 || selection.isCollapsed) {
      hidePopover();
      return;
    }

    if (isSelectionInEditableArea(selection)) {
      hidePopover();
      return;
    }

    const selectedText = selection.toString().trim();
    if (!selectedText) {
      hidePopover();
      return;
    }

    const range = selection.getRangeAt(0);
    const selectionRect = getVisibleSelectionRect(range);
    if (!selectionRect) {
      hidePopover();
      return;
    }

    const { left, top } = getSelectionPopoverPosition({
      selectionRect,
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
      menuWidth: MENU_WIDTH,
      menuHeight: MENU_HEIGHT,
    });

    latestTextRef.current = selectedText;
    setPopover({ selectedText, left, top });
  }, [hidePopover]);

  useEffect(() => {
    let timer: number | null = null;
    const scheduleUpdate = () => {
      if (timer !== null) window.clearTimeout(timer);
      timer = window.setTimeout(updateFromSelection, 40);
    };

    document.addEventListener("mouseup", scheduleUpdate);
    document.addEventListener("keyup", scheduleUpdate);
    document.addEventListener("touchend", scheduleUpdate);
    window.addEventListener("resize", hidePopover);
    window.addEventListener("scroll", hidePopover, true);

    return () => {
      if (timer !== null) window.clearTimeout(timer);
      document.removeEventListener("mouseup", scheduleUpdate);
      document.removeEventListener("keyup", scheduleUpdate);
      document.removeEventListener("touchend", scheduleUpdate);
      window.removeEventListener("resize", hidePopover);
      window.removeEventListener("scroll", hidePopover, true);
    };
  }, [hidePopover, updateFromSelection]);

  const handleAction = (action: SelectionAction) => {
    const selectedText = latestTextRef.current || popover?.selectedText || "";
    if (!selectedText) return;

    const prompt = buildSelectionActionPrompt({
      action,
      selectedText,
      templates: {
        ask: t("selectionActions.askPrompt"),
        explain: t("selectionActions.explainPrompt"),
      },
    });

    if (location.pathname.startsWith("/chat")) {
      dispatchSelectionActionPrompt(prompt);
    } else {
      storePendingSelectionActionPrompt(prompt);
      navigate("/chat");
    }

    window.getSelection()?.removeAllRanges();
    hidePopover();
  };

  if (!popover) return null;

  return (
    <div
      ref={popoverRef}
      data-selection-action-popover="true"
      className="fixed rounded-lg text-xs z-[9999]"
      style={{ left: popover.left, top: popover.top }}
    >
      <div className="flex flex-row gap-0.5 shrink-0 p-1 bg-white text-stone-700 dark:bg-stone-800 dark:text-stone-100 text-medium rounded-lg shadow-xl border border-stone-100 dark:border-stone-700">
        <button
          type="button"
          className="px-1.5 py-1 hover:bg-stone-50 dark:hover:bg-stone-700 rounded flex items-center gap-1 min-w-fit transition-colors"
          title={t("selectionActions.ask")}
          aria-label={t("selectionActions.ask")}
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => handleAction("ask")}
        >
          <MessageCircle className="size-3 shrink-0" strokeWidth={1.5} />
          <span className="shrink-0">{t("selectionActions.ask")}</span>
        </button>
        <button
          type="button"
          className="px-1.5 py-1 hover:bg-stone-50 dark:hover:bg-stone-700 rounded flex items-center gap-1 min-w-fit transition-colors"
          title={t("selectionActions.explain")}
          aria-label={t("selectionActions.explain")}
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => handleAction("explain")}
        >
          <Lightbulb className="size-3 shrink-0" strokeWidth={1.5} />
          <span className="shrink-0">{t("selectionActions.explain")}</span>
        </button>
      </div>
    </div>
  );
}
