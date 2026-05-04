import { createPortal } from "react-dom";
import { Users, Sparkles, User } from "lucide-react";
import type { ScopeFilter } from "./usePersonaPlaza";

interface ScopeTab {
  key: ScopeFilter;
  label: string;
  icon: "Users" | "Sparkles" | "User";
  count: number;
}

const ICON_MAP = {
  Users,
  Sparkles,
  User,
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
  if (!isOpen || !scopeBtnRef.current) return null;

  return createPortal(
    <div className="fixed inset-0 z-[999]" onMouseDown={onClose}>
      <div
        className="absolute w-44 rounded-xl border bg-[var(--theme-bg-card,#1c1917)] p-1 shadow-lg"
        style={{
          top: scopeBtnRef.current.getBoundingClientRect().bottom + 8,
          left: scopeBtnRef.current.getBoundingClientRect().right - 176,
        }}
        onMouseDown={(e) => e.stopPropagation()}
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
              <span
                className="text-xs"
                style={{ color: "var(--theme-text-secondary)" }}
              >
                {count}
              </span>
            </button>
          );
        })}
      </div>
    </div>,
    document.body,
  );
}
