import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { Check, Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import { getMentionPopupFixedPlacement } from "./chatInputViewport";
import { useStickyDropdownPosition } from "../../hooks/useStickyDropdownPosition";
import { getCategoryIcon, nameToGradient } from "../common/cardUtils";
import { getAnchoredSlashDropdownPlacement } from "./slashDropdownPlacement";
import type {
  SlashDropdownItem,
  SlashDropdownSection,
} from "./chatInputSlashCommands";

export interface SlashDropdownMenuProps {
  open: boolean;
  sections: SlashDropdownSection[];
  items: SlashDropdownItem[];
  runSkillNameSet: Set<string>;
  containerRef: React.RefObject<HTMLDivElement | null>;
  anchorRect?: DOMRect | null;
  onApplySelection: (item: SlashDropdownItem) => void;
  onDismiss?: () => void;
  highlightIndex: number;
  onHighlightChange: React.Dispatch<React.SetStateAction<number>>;
}

export function SlashDropdownMenu({
  open,
  sections,
  items,
  runSkillNameSet,
  containerRef,
  anchorRect,
  onApplySelection,
  onDismiss,
  highlightIndex,
  onHighlightChange,
}: SlashDropdownMenuProps) {
  const { t } = useTranslation();
  const popupRef = useRef<HTMLDivElement>(null);

  // Reset highlight when items change
  useEffect(() => {
    onHighlightChange(0);
  }, [items.length, onHighlightChange]);

  // Scroll highlighted item into view when navigating with arrow keys
  useEffect(() => {
    if (!open) return;
    const el = popupRef.current?.querySelector(
      `[data-slash-idx="${highlightIndex}"]`,
    );
    if (el) {
      (el as HTMLElement).scrollIntoView?.({ block: "nearest" });
    }
  }, [open, highlightIndex]);

  useEffect(() => {
    if (!open) return;
    const handleMouseDown = (event: MouseEvent) => {
      const target = event.target;
      if (target instanceof Node && popupRef.current?.contains(target)) return;
      onDismiss?.();
    };
    document.addEventListener("mousedown", handleMouseDown);
    return () => document.removeEventListener("mousedown", handleMouseDown);
  }, [onDismiss, open]);

  // Compute placement before any early return — hooks must not be called conditionally
  const placement = useStickyDropdownPosition(containerRef, open, (rect) => {
    const pos = getMentionPopupFixedPlacement({
      inputRect: rect ?? null,
      viewportHeight: window.visualViewport?.height ?? window.innerHeight,
    });
    if (!pos) return { display: "none" };
    return {
      left: pos.left,
      width: Math.min(pos.width, 320),
      bottom: pos.bottom,
      maxHeight: pos.maxHeight,
    };
  });

  const estimatedMenuHeight = Math.min(
    320,
    16 + items.length * 40 + (sections.length > 1 ? sections.length * 30 : 0),
  );
  const viewportWidth =
    typeof window === "undefined" ? 1024 : window.innerWidth;
  const viewportHeight =
    typeof window === "undefined"
      ? 768
      : window.visualViewport?.height ?? window.innerHeight;
  const compactMobile = viewportWidth < 640;
  const menuHeight = compactMobile
    ? Math.min(estimatedMenuHeight, 240, Math.round(viewportHeight * 0.42))
    : estimatedMenuHeight;
  const menuWidth = compactMobile ? 288 : 320;
  const viewportMargin = compactMobile ? 12 : 8;
  const anchoredPlacement = anchorRect
    ? getAnchoredSlashDropdownPlacement(
        anchorRect,
        viewportWidth,
        viewportHeight,
        menuHeight,
        menuWidth,
        viewportMargin,
      )
    : null;

  if (!open) return null;

  const renderSections = () =>
    sections.map((section) => {
      let sectionStart = 0;
      for (const prev of sections) {
        if (prev === section) break;
        sectionStart += prev.items.length;
      }

      return (
        <div key={section.kind}>
          {sections.length > 1 && (
            <div
              className="px-3 py-1.5 text-11 font-medium uppercase tracking-wider"
              style={{ color: "var(--theme-text-secondary)" }}
            >
              {t(section.labelKey, section.fallbackLabel)}
            </div>
          )}
          {section.items.map((item, idx) => {
            const globalIndex = sectionStart + idx;
            const isHighlighted = globalIndex === highlightIndex;

            return (
              <button
                key={
                  item.type === "command"
                    ? `cmd-${item.command.id}`
                    : `skill-${item.skill.name}`
                }
                data-slash-idx={globalIndex}
                type="button"
                role="option"
                aria-selected={isHighlighted}
                onMouseDown={(e) => {
                  e.preventDefault();
                  onApplySelection(item);
                }}
                className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-13 transition-colors"
                style={{
                  backgroundColor: isHighlighted
                    ? "var(--theme-bg-hover, rgba(128,128,128,0.08))"
                    : "transparent",
                }}
                onMouseEnter={() => onHighlightChange(globalIndex)}
              >
                {item.type === "command" ? (
                  <>
                    <item.command.icon
                      size={14}
                      className="shrink-0"
                      style={{ color: "var(--theme-text-secondary)" }}
                    />
                    <span className="font-medium shrink-0">
                      {t(item.command.labelKey, item.command.fallbackLabel)}
                    </span>
                    {item.command.fallbackDescription && (
                      <span
                        className="slash-command-description min-w-0 flex-1 truncate"
                        style={{ color: "var(--theme-text-secondary)" }}
                      >
                        {t(
                          item.command.descriptionKey ?? "",
                          item.command.fallbackDescription,
                        )}
                      </span>
                    )}
                  </>
                ) : (
                  (() => {
                    const SkillIcon = item.skill.tags[0]
                      ? getCategoryIcon(item.skill.tags[0])
                      : Sparkles;
                    const gradient = nameToGradient(item.skill.name);
                    const isSelected = runSkillNameSet.has(item.skill.name);
                    return (
                      <>
                        <div
                          className="shrink-0 flex items-center justify-center size-6 rounded-md"
                          style={{
                            background: `linear-gradient(135deg, ${gradient[0]}66, ${gradient[1]}66)`,
                            opacity: isSelected ? 1 : 0.5,
                          }}
                        >
                          <SkillIcon size={12} className="text-white" />
                        </div>
                        <span className="min-w-0 flex-1 truncate">
                          {item.skill.name}
                        </span>
                        {isSelected && (
                          <Check
                            size={14}
                            className="shrink-0"
                            style={{ color: "var(--theme-primary)" }}
                          />
                        )}
                      </>
                    );
                  })()
                )}
              </button>
            );
          })}
        </div>
      );
    });

  // Render at the document root so transformed/stacked chat layouts cannot
  // clip the menu or intercept its pointer events.
  if (typeof document === "undefined") return null;

  if ("display" in placement && placement.display === "none") {
    return createPortal(
      <div
        ref={popupRef}
        role="listbox"
        aria-label="Slash commands"
        className="slash-command-menu fixed bottom-20 left-2 z-[350] overflow-hidden rounded-xl border shadow-lg"
        style={{
          backgroundColor: "var(--theme-bg-card)",
          borderColor: "var(--theme-border)",
          color: "var(--theme-text)",
          width: menuWidth,
          maxWidth: `calc(100vw - ${viewportMargin * 2}px)`,
          maxHeight: menuHeight,
          pointerEvents: "auto",
        }}
      >
        {renderSections()}
      </div>,
      document.body,
    );
  }

  const resolvedPlacement = anchoredPlacement ?? placement;
  return createPortal(
    <div
      ref={popupRef}
      role="listbox"
      aria-label="Slash commands"
      className="slash-command-menu fixed z-[350] overflow-hidden rounded-xl border shadow-lg"
      style={{
        ...resolvedPlacement,
        backgroundColor: "var(--theme-bg-card)",
        borderColor: "var(--theme-border)",
        color: "var(--theme-text)",
        pointerEvents: "auto",
      }}
    >
      <div
        className="overflow-y-auto"
        style={{ maxHeight: resolvedPlacement.maxHeight }}
      >
        {renderSections()}
      </div>
    </div>,
    document.body,
  );
}
