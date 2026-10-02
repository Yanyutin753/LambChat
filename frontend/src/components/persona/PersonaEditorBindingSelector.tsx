import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { Check, ChevronDown, Loader2, Plus, Search, X } from "lucide-react";
import { useStickyDropdownPosition } from "../../hooks/useStickyDropdownPosition";
import { PanelSearchInput } from "../common/PanelSearchInput";
import { Button, IconButton } from "../common/ui";

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
  disabled?: boolean;
  error?: boolean;
  onRetry?: () => void;
  searchValue?: string;
  onSearchChange?: (query: string) => void;
  onScroll?: React.UIEventHandler<HTMLDivElement>;
  triggerClassName?: string;
}

/** Shared capability picker for persona skills and MCP bindings. */
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
  disabled = false,
  error = false,
  onRetry,
  searchValue,
  onSearchChange,
  onScroll,
  triggerClassName = "",
}: BindingSelectorProps) {
  const { t } = useTranslation();
  const [localSearch, setLocalSearch] = useState("");
  const search = searchValue ?? localSearch;
  const setSearch = onSearchChange ?? setLocalSearch;
  const triggerRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const listId = useId();

  useEffect(() => {
    if (!open) {
      setSearch("");
      return;
    }
    const outside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        !triggerRef.current?.contains(target) &&
        !dropdownRef.current?.contains(target)
      )
        onOpenChange(false);
    };
    document.addEventListener("mousedown", outside);
    return () => document.removeEventListener("mousedown", outside);
  }, [open, onOpenChange, setSearch]);

  const dropdownStyle = useStickyDropdownPosition(triggerRef, open, (rect) => {
    const viewport = window.visualViewport;
    const leftEdge = viewport?.offsetLeft ?? 0;
    const topEdge = viewport?.offsetTop ?? 0;
    const viewportWidth = viewport?.width ?? window.innerWidth;
    const viewportBottom = topEdge + (viewport?.height ?? window.innerHeight);
    const width = Math.min(
      Math.max(rect.width, 280),
      Math.max(0, viewportWidth - 24),
    );
    const anchorTop = Math.max(
      topEdge + 12,
      Math.min(rect.top, viewportBottom - 12),
    );
    const anchorBottom = Math.max(
      topEdge + 12,
      Math.min(rect.bottom, viewportBottom - 12),
    );
    const below = viewportBottom - anchorBottom - 12;
    const above = anchorTop - topEdge - 12;
    const openBelow = below >= 240 || below >= above;
    if (Math.max(below, above) < 240) {
      return {
        position: "fixed",
        top: topEdge + 12,
        left: leftEdge + 12,
        width: Math.max(0, viewportWidth - 24),
        maxHeight: Math.max(0, viewportBottom - topEdge - 24),
        zIndex: 9999,
      };
    }
    return {
      position: "fixed",
      top: openBelow ? anchorBottom + 4 : undefined,
      bottom: openBelow ? undefined : window.innerHeight - anchorTop + 4,
      left: Math.max(
        leftEdge + 12,
        Math.min(rect.left, leftEdge + viewportWidth - width - 12),
      ),
      width,
      maxHeight: Math.min(400, Math.max(0, openBelow ? below : above)),
      zIndex: 9999,
    };
  });

  const keyword = search.trim().toLowerCase();
  // Server-backed skills already filter the query; local MCP options filter here.
  const filtered =
    onSearchChange || !keyword
      ? options
      : options.filter(
          (option) =>
            option.name.toLowerCase().includes(keyword) ||
            (option.description ?? "").toLowerCase().includes(keyword),
        );
  const displayed = [...filtered].sort(
    (a, b) =>
      Number(selected.includes(b.name)) - Number(selected.includes(a.name)) ||
      a.name.localeCompare(b.name),
  );
  const close = () => {
    onOpenChange(false);
    triggerRef.current?.focus();
  };

  const selectedChips = selected.map((name) => (
    <span key={name} className="ppe-skill-chip">
      <span className="ppe-skill-chip__name">{name}</span>
      <button
        type="button"
        className="ppe-skill-chip-remove"
        aria-label={`${t("common.remove")} ${name}`}
        onClick={() => {
          (open ? searchInputRef.current : triggerRef.current)?.focus();
          onChange((prev) => prev.filter((n) => n !== name));
        }}
      >
        <X size={11} aria-hidden="true" />
      </button>
    </span>
  ));

  return (
    <div className="relative min-w-0">
      <button
        ref={triggerRef}
        type="button"
        disabled={disabled}
        onClick={() => onOpenChange(!open)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        className={`ppe-skill-trigger ${
          open ? "ppe-skill-trigger--open" : ""
        } ${triggerClassName}`}
      >
        {selected.length > 0 ? (
          <span className="ppe-skill-trigger__count">
            {icon}
            {t(countLabelKey, { count: selected.length })}
          </span>
        ) : (
          <span className="ppe-skill-trigger__placeholder">
            {t(placeholderKey)}
          </span>
        )}
        <ChevronDown
          size={14}
          aria-hidden="true"
          className={`ppe-skill-trigger__chevron ${open ? "rotate-180" : ""}`}
        />
      </button>
      {selected.length > 0 && !open && (
        <div className="ppe-skill-selected-area">{selectedChips}</div>
      )}
      {open &&
        createPortal(
          <div
            ref={dropdownRef}
            className="ppe-skill-dropdown"
            style={dropdownStyle}
            onKeyDown={(event) => {
              if (event.nativeEvent.isComposing || event.keyCode === 229) {
                event.stopPropagation();
                return;
              }
              if (event.key === "Escape") {
                event.preventDefault();
                event.stopPropagation();
                close();
                return;
              }
              if (event.key === "Tab") {
                const controls = [
                  ...event.currentTarget.querySelectorAll<HTMLElement>(
                    "input:not(:disabled), button:not(:disabled)",
                  ),
                ];
                if (
                  document.activeElement ===
                  (event.shiftKey ? controls[0] : controls.at(-1))
                ) {
                  event.preventDefault();
                  event.stopPropagation();
                  close();
                }
                return;
              }
              const options = [
                ...event.currentTarget.querySelectorAll<HTMLButtonElement>(
                  '[role="option"]',
                ),
              ];
              const index = options.indexOf(
                document.activeElement as HTMLButtonElement,
              );
              if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                event.preventDefault();
                event.stopPropagation();
                const next =
                  event.key === "ArrowDown"
                    ? options[(index + 1) % options.length]
                    : options[index - 1];
                (next ?? searchInputRef.current)?.focus();
              } else if (
                index >= 0 &&
                (event.key === "Home" || event.key === "End")
              ) {
                event.preventDefault();
                options[event.key === "Home" ? 0 : options.length - 1]?.focus();
              }
            }}
          >
            <div className="ppe-skill-dropdown__header">
              <div className="ppe-skill-dropdown__search-wrap">
                <Search
                  size={14}
                  className="ppe-skill-dropdown__search-icon"
                  aria-hidden="true"
                />
                <PanelSearchInput
                  ref={searchInputRef}
                  value={search}
                  onValueChange={setSearch}
                  placeholder={t(searchPlaceholderKey)}
                  className="ppe-skill-search"
                  autoFocus
                  role="combobox"
                  aria-expanded={open}
                  aria-controls={listId}
                />
              </div>
              {selected.length > 0 && (
                <button
                  type="button"
                  className="ppe-skill-dropdown__clear-all"
                  onClick={() => {
                    searchInputRef.current?.focus();
                    onChange(() => []);
                  }}
                >
                  {t("common.clearAll", "清除全部")}
                </button>
              )}
              <IconButton
                size="sm"
                icon={<X size={14} aria-hidden="true" />}
                aria-label={t("common.close")}
                title={t("common.close")}
                onClick={close}
              />
            </div>
            {selected.length > 0 && Number(dropdownStyle.maxHeight) >= 280 && (
              <div className="ppe-skill-selected-bar">{selectedChips}</div>
            )}
            <div
              className="ppe-skill-dropdown__list"
              role="listbox"
              id={listId}
              aria-label={t(placeholderKey)}
              aria-multiselectable="true"
              aria-busy={loading}
              onScroll={onScroll}
            >
              {displayed.map((option) => {
                const isSelected = selected.includes(option.name);
                return (
                  <button
                    key={option.name}
                    type="button"
                    role="option"
                    aria-selected={isSelected}
                    className={`ppe-skill-option ${
                      isSelected ? "ppe-skill-option--selected" : ""
                    }`}
                    onClick={() =>
                      onChange((prev) =>
                        prev.includes(option.name)
                          ? prev.filter((n) => n !== option.name)
                          : [...prev, option.name],
                      )
                    }
                  >
                    <div className="ppe-skill-option__check-ring">
                      {isSelected ? (
                        <Check
                          size={12}
                          className="ppe-skill-option__check-icon"
                          aria-hidden="true"
                        />
                      ) : (
                        <Plus
                          size={12}
                          className="ppe-skill-option__plus-icon"
                          aria-hidden="true"
                        />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="break-words [overflow-wrap:anywhere] font-serif text-14 font-medium">
                        {option.name}
                      </div>
                      {option.description && (
                        <div className="mt-0.5 truncate text-11 text-theme-text-secondary">
                          {option.description}
                        </div>
                      )}
                    </div>
                  </button>
                );
              })}
            </div>
            {loading ? (
              <div className="ppe-skill-dropdown__loading" role="status">
                <Loader2
                  size={14}
                  className="animate-spin"
                  aria-hidden="true"
                />
                <span>{t("common.loading")}</span>
              </div>
            ) : error ? (
              <div role="alert" className="ppe-skill-dropdown__loading">
                <span>{t("common.loadFailed")}</span>
                <Button
                  size="sm"
                  className="!min-h-11"
                  onClick={() => {
                    searchInputRef.current?.focus();
                    onRetry?.();
                  }}
                >
                  {t("common.retry")}
                </Button>
              </div>
            ) : (
              displayed.length === 0 && (
                <div className="ppe-skill-dropdown__empty">{t(emptyKey)}</div>
              )
            )}
          </div>,
          document.body,
        )}
    </div>
  );
}
