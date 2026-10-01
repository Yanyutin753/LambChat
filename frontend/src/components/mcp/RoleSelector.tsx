import { useState, useEffect, useRef, useCallback, useId } from "react";
import { createPortal } from "react-dom";
import { ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import { roleApi } from "../../services/api/role";
import { useStickyDropdownPosition } from "../../hooks/useStickyDropdownPosition";
import { PanelSearchInput } from "../common/PanelSearchInput";
import { Button, Checkbox } from "../common";
import { McpSelectorEmptyState } from "./McpSelectorEmptyState";

interface RoleSelectorProps {
  selectedRoles: string[];
  onChange: (roles: string[]) => void;
}
interface RoleInfo {
  name: string;
  description?: string;
  is_system: boolean;
}
export function RoleSelector({ selectedRoles, onChange }: RoleSelectorProps) {
  const { t } = useTranslation();
  const [availableRoles, setAvailableRoles] = useState<RoleInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState("");
  const triggerRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const labelId = useId();
  const loadRoles = useCallback(() => {
    setLoading(true);
    setLoadError(false);
    roleApi
      .list({ limit: 200 })
      .then((response) => setAvailableRoles(response.roles))
      .catch(() => setLoadError(true))
      .finally(() => setLoading(false));
  }, []);
  useEffect(loadRoles, [loadRoles]);
  useEffect(() => {
    if (!isOpen) return;
    const outside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        !triggerRef.current?.contains(target) &&
        !dropdownRef.current?.contains(target)
      ) {
        setIsOpen(false);
        setSearch("");
      }
    };
    document.addEventListener("mousedown", outside);
    return () => document.removeEventListener("mousedown", outside);
  }, [isOpen]);
  const dropdownStyle = useStickyDropdownPosition(
    triggerRef,
    isOpen,
    (rect) => {
      const height = window.visualViewport?.height ?? window.innerHeight;
      const offsetTop = window.visualViewport?.offsetTop ?? 0;
      const viewportWidth = window.visualViewport?.width ?? window.innerWidth;
      const below = offsetTop + height - rect.bottom - 16;
      const above = rect.top - offsetTop - 16;
      const openBelow = below >= 240 || below >= above;
      const width = Math.min(rect.width, viewportWidth - 24);
      return {
        position: "fixed",
        top: openBelow ? rect.bottom + 4 : undefined,
        bottom: openBelow ? undefined : window.innerHeight - rect.top + 4,
        left: Math.max(12, Math.min(rect.left, viewportWidth - width - 12)),
        width,
        maxHeight: Math.min(320, Math.max(0, openBelow ? below : above)),
        zIndex: 9999,
      };
    },
  );
  const filteredRoles = availableRoles.filter((role) =>
    role.name.toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <div className="ui-select">
      <button
        ref={triggerRef}
        type="button"
        aria-label={t("mcp.form.allowedRoles")}
        aria-describedby={labelId}
        aria-expanded={isOpen}
        className="ui-select-trigger min-h-11 sm:min-h-[38px]"
        onClick={() => setIsOpen(!isOpen)}
      >
        <span id={labelId} className="min-w-0 flex-1 truncate text-left">
          {selectedRoles.length
            ? selectedRoles.join(", ")
            : t("mcp.form.allRoles")}
        </span>
        <ChevronDown size={15} className="ui-select-trigger__icon" />
      </button>
      {isOpen &&
        createPortal(
          <div
            ref={dropdownRef}
            role="group"
            aria-label={t("mcp.form.allowedRoles")}
            className="ui-select-dropdown flex flex-col overflow-hidden"
            style={dropdownStyle}
            onKeyDown={(event) => {
              if (event.key === "Tab") {
                const controls = [
                  ...event.currentTarget.querySelectorAll<HTMLElement>(
                    "input:not(:disabled),button:not(:disabled)",
                  ),
                ];
                const boundary = event.shiftKey ? controls[0] : controls.at(-1);
                if (document.activeElement !== boundary) return;
              } else if (event.key === "Escape") {
                event.preventDefault();
              } else return;
              event.stopPropagation();
              setIsOpen(false);
              setSearch("");
              triggerRef.current?.focus();
            }}
          >
            <PanelSearchInput
              value={search}
              onValueChange={setSearch}
              aria-label={t("mcp.form.searchRoles")}
              placeholder={t("mcp.form.searchRoles")}
              className="ui-input !min-h-11 shrink-0"
              autoFocus
            />
            <div className="min-h-0 flex-1 overflow-y-auto py-1">
              {loading ? (
                <McpSelectorEmptyState>
                  {t("common.loading")}
                </McpSelectorEmptyState>
              ) : loadError ? (
                <div
                  role="alert"
                  className="flex flex-wrap items-center justify-between gap-2 p-2 text-12 text-theme-text-secondary"
                >
                  <span>{t("common.loadFailed")}</span>
                  <Button size="sm" onClick={loadRoles} className="!min-h-11">
                    {t("common.refresh")}
                  </Button>
                </div>
              ) : !availableRoles.length ? (
                <McpSelectorEmptyState>
                  {t("mcp.form.noRoles")}
                </McpSelectorEmptyState>
              ) : !filteredRoles.length ? (
                <McpSelectorEmptyState>
                  {t("mcp.form.noMatchingRoles")}
                </McpSelectorEmptyState>
              ) : (
                filteredRoles.map((role) => (
                  <label
                    key={role.name}
                    className="flex min-h-11 cursor-pointer items-center gap-2 rounded-md px-2 py-2 hover:bg-[var(--theme-bg-subtle)]"
                  >
                    <Checkbox
                      size="sm"
                      ariaLabel={role.name}
                      checked={selectedRoles.includes(role.name)}
                      onChange={() =>
                        onChange(
                          selectedRoles.includes(role.name)
                            ? selectedRoles.filter((name) => name !== role.name)
                            : [...selectedRoles, role.name],
                        )
                      }
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block break-words text-12 font-medium text-theme-text">
                        {role.name}
                      </span>
                      {role.description && (
                        <span className="block truncate text-10 text-theme-text-muted">
                          {role.description}
                        </span>
                      )}
                    </span>
                    {role.is_system && (
                      <span className="shrink-0 text-10 text-theme-text-muted">
                        {t("mcp.card.system")}
                      </span>
                    )}
                  </label>
                ))
              )}
            </div>
            {selectedRoles.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                className="!min-h-11 shrink-0"
                onClick={() => {
                  onChange([]);
                  dropdownRef.current?.querySelector("input")?.focus();
                }}
              >
                {t("mcp.form.clearAll")}
              </Button>
            )}
          </div>,
          document.body,
        )}
    </div>
  );
}
