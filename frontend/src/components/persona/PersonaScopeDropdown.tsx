import { createPortal } from "react-dom";
import { useEffect, type CSSProperties } from "react";
import { Users, Sparkles, User, Pin, Star } from "lucide-react";
import { useStickyDropdownPosition } from "../../hooks/useStickyDropdownPosition";
import type { ScopeFilter } from "./usePersonaPlaza";

interface ScopeTab {
  key: ScopeFilter;
  label: string;
  icon: "Users" | "Sparkles" | "User" | "Pin" | "Star";
  count?: number;
}

const ICON_MAP = {
  Users,
  Sparkles,
  User,
  Pin,
  Star,
} as const;

const DROPDOWN_GUTTER = 12;
const SCOPE_DROPDOWN_WIDTH = 192;

function getDropdownPosition(rect: DOMRect, width: number): CSSProperties {
  const availableWidth = window.innerWidth - DROPDOWN_GUTTER * 2;
  const renderedWidth = Math.min(width, availableWidth);
  const left = Math.min(
    Math.max(DROPDOWN_GUTTER, rect.right - renderedWidth),
    window.innerWidth - renderedWidth - DROPDOWN_GUTTER,
  );
  const top = rect.bottom + 8;

  return {
    top,
    left,
    width: renderedWidth,
    maxHeight: `calc(100dvh - ${top + DROPDOWN_GUTTER}px)`,
  };
}

interface PersonaScopeDropdownProps {
  isOpen: boolean;
  scopeFilter: ScopeFilter;
  scopeTabs: ScopeTab[];
  scopeBtnRef: React.RefObject<HTMLButtonElement | null>;
  onSelect: (key: ScopeFilter) => void;
  onClose: () => void;
}

export function PersonaScopeDropdown({
  isOpen,
  scopeFilter,
  scopeTabs,
  scopeBtnRef,
  onSelect,
  onClose,
}: PersonaScopeDropdownProps) {
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  // Compute style before any early return — hooks must not be called conditionally
  const dropdownStyle = useStickyDropdownPosition(scopeBtnRef, isOpen, (rect) =>
    getDropdownPosition(rect, SCOPE_DROPDOWN_WIDTH),
  );

  if (!isOpen) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[999]"
      data-panel-header-dropdown
      onPointerDown={onClose}
    >
      <div
        className="panel-header-dropdown fixed overflow-y-auto rounded-xl border bg-[var(--theme-bg-card,#1c1917)] p-1 shadow-lg"
        role="menu"
        style={dropdownStyle}
        onPointerDown={(e) => e.stopPropagation()}
      >
        {scopeTabs.map(({ key, label, icon, count }) => {
          const Icon = ICON_MAP[icon];
          return (
            <button
              key={key}
              type="button"
              onClick={() => {
                onSelect(key);
                onClose();
              }}
              role="menuitemradio"
              aria-checked={scopeFilter === key}
              className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors"
              style={{
                background:
                  scopeFilter === key
                    ? "var(--skill-surface-alt)"
                    : "var(--theme-bg-card, #1c1917)",
                color:
                  scopeFilter === key
                    ? "var(--theme-text)"
                    : "var(--theme-text-secondary)",
              }}
            >
              <Icon size={14} />
              <span className="flex-1 text-left">{label}</span>
              {typeof count === "number" && (
                <span
                  className="text-xs"
                  style={{ color: "var(--theme-text-secondary)" }}
                >
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>,
    document.body,
  );
}
