import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, ChevronDown, Loader2, Plus, X } from "lucide-react";
import { PanelSearchInput } from "../common/PanelSearchInput";

export interface BindingOption {
  name: string;
  description?: string | null;
}

interface BindingSelectorProps {
  options: BindingOption[];
  selected: string[];
  onChange: (updater: (prev: string[]) => string[]) => void;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  icon: React.ReactNode;
  countLabelKey: string;
  placeholderKey: string;
  searchPlaceholderKey: string;
  emptyKey: string;
  loading?: boolean;
  triggerClassName?: string;
}

/**
 * 角色（persona）能力绑定选择器：插件绑定 / MCP server 绑定共用。
 * 交互与视觉对齐 PersonaEditorSkillSelector 的 chip + dropdown 模式。
 */
export function PersonaEditorBindingSelector({
  options,
  selected,
  onChange,
  open,
  onOpenChange,
  icon,
  countLabelKey,
  placeholderKey,
  searchPlaceholderKey,
  emptyKey,
  loading = false,
  triggerClassName = "",
}: BindingSelectorProps) {
  const { t } = useTranslation();
  const [search, setSearch] = useState("");
  const dropdownRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (open && dropdownRef.current && !dropdownRef.current.contains(target)) {
        onOpenChange(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open, onOpenChange]);

  useEffect(() => {
    if (!open) {
      setSearch("");
    }
  }, [open]);

  const keyword = search.trim().toLowerCase();
  const filtered = keyword
    ? options.filter(
        (option) =>
          option.name.toLowerCase().includes(keyword) ||
          (option.description ?? "").toLowerCase().includes(keyword),
      )
    : options;
  const displayed = [...filtered].sort((a, b) => {
    const aSel = selected.includes(a.name) ? 0 : 1;
    const bSel = selected.includes(b.name) ? 0 : 1;
    return aSel - bSel || a.name.localeCompare(b.name);
  });

  const toggle = (name: string) => {
    onChange((prev) =>
      prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name],
    );
  };

  const remove = (name: string) => {
    onChange((prev) => prev.filter((n) => n !== name));
  };

  return (
    <div ref={dropdownRef} className="relative">
      <button
        type="button"
        onClick={() => onOpenChange(!open)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className={`ppe-skill-trigger ${open ? "ppe-skill-trigger--open" : ""} ${triggerClassName}`}
      >
        {selected.length > 0 ? (
          <span className="ppe-skill-trigger__count">
            {icon}
            {t(countLabelKey, { count: selected.length })}
          </span>
        ) : (
          <span className="ppe-skill-trigger__placeholder">{t(placeholderKey)}</span>
        )}
        <ChevronDown
          size={14}
          className={`ppe-skill-trigger__chevron ${open ? "rotate-180" : ""}`}
        />
      </button>

      {selected.length > 0 && !open && (
        <div className="ppe-skill-selected-area">
          {selected.map((name) => (
            <span key={name} className="ppe-skill-chip">
              {name}
              <X
                size={11}
                className="ppe-skill-chip-remove"
                onClick={() => remove(name)}
              />
            </span>
          ))}
        </div>
      )}

      {open && (
        <div className="ppe-skill-dropdown">
          <div className="ppe-skill-dropdown__header">
            <div className="ppe-skill-dropdown__search-wrap">
              <PanelSearchInput
                ref={searchInputRef}
                type="text"
                value={search}
                onValueChange={setSearch}
                placeholder={t(searchPlaceholderKey)}
                className="ppe-skill-search"
                autoFocus
                role="combobox"
                aria-expanded={open}
              />
            </div>
            {selected.length > 0 && (
              <button
                type="button"
                className="ppe-skill-dropdown__clear-all"
                onClick={() => onChange(() => [])}
              >
                {t("common.clearAll", "清除全部")}
              </button>
            )}
          </div>

          <div className="ppe-skill-dropdown__list" role="listbox">
            {displayed.length > 0 ? (
              displayed.map((option) => {
                const isSelected = selected.includes(option.name);
                return (
                  <button
                    key={option.name}
                    type="button"
                    onClick={() => toggle(option.name)}
                    className={`ppe-skill-option ${isSelected ? "ppe-skill-option--selected" : ""}`}
                    role="option"
                    aria-selected={isSelected}
                  >
                    <div className="ppe-skill-option__check-ring">
                      {isSelected ? (
                        <Check size={12} className="ppe-skill-option__check-icon" />
                      ) : (
                        <Plus size={12} className="ppe-skill-option__plus-icon" />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-serif text-14 font-medium">
                        {option.name}
                      </div>
                      {option.description && (
                        <div className="mt-0.5 truncate text-11 text-[var(--theme-text-secondary)]">
                          {option.description}
                        </div>
                      )}
                    </div>
                  </button>
                );
              })
            ) : (
              <div className="ppe-skill-dropdown__empty">
                {loading ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <span>{t(emptyKey)}</span>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
