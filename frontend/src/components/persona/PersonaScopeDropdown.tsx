import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { Users, Sparkles, User, Pin, Star } from "lucide-react";
import { usePanelFilterMenu } from "../../hooks/usePanelFilterMenu";
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
  const { t } = useTranslation();
  const { menuRef, dropdownStyle, ready, onKeyDown, closeMenu } =
    usePanelFilterMenu(scopeBtnRef, isOpen, 192, onClose);

  if (!ready) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[999]"
      data-panel-header-dropdown
      onPointerDown={closeMenu}
    >
      <div
        className="panel-header-dropdown fixed overflow-y-auto rounded-xl border bg-[var(--theme-bg-card,#1c1917)] p-1 shadow-lg"
        ref={menuRef}
        tabIndex={-1}
        onKeyDown={onKeyDown}
        role="menu"
        aria-label={t("personaPresets.scope")}
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
                closeMenu();
              }}
              role="menuitemradio"
              aria-checked={scopeFilter === key}
              className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-14 transition-colors"
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
                  className="text-12"
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
