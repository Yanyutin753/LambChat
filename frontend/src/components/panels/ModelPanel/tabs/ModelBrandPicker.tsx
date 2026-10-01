import { useEffect, useRef, useState, useId } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { Input, PickerTrigger } from "../../../common";
import { PanelSearchInput } from "../../../common/PanelSearchInput";
import { ModelIconImg } from "../../../agent/modelIcon.tsx";
import { useStickyDropdownPosition } from "../../../../hooks/useStickyDropdownPosition";
import { PROVIDER_LABELS } from "../../AgentPanel/shared/providerLabels";

interface ModelBrandPickerProps {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  slugs: string[];
  kind: "provider" | "icon";
  loading?: boolean;
  className?: string;
}

export function ModelBrandPicker({
  value,
  onChange,
  placeholder,
  slugs,
  kind,
  loading = false,
  className = "",
}: ModelBrandPickerProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);
  const popupRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const valueId = useId();
  const selected = slugs.includes(value) ? value : null;
  const ariaLabel = t(
    kind === "provider" ? "agentConfig.modelProvider" : "agentConfig.modelIcon",
  );
  const label = (slug: string) => PROVIDER_LABELS[slug] || slug;
  const filtered = slugs.filter(
    (slug) =>
      !search.trim() ||
      `${slug} ${label(slug)}`
        .toLowerCase()
        .includes(search.trim().toLowerCase()),
  );
  const popupStyle = useStickyDropdownPosition(containerRef, open, (rect) => {
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
  });
  const close = () => {
    setOpen(false);
    setSearch("");
    containerRef.current?.querySelector("button")?.focus();
  };
  useEffect(() => {
    if (!open) return;
    searchRef.current?.focus();
    const outside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        !containerRef.current?.contains(target) &&
        !popupRef.current?.contains(target)
      ) {
        setOpen(false);
        setSearch("");
      }
    };
    document.addEventListener("mousedown", outside);
    return () => document.removeEventListener("mousedown", outside);
  }, [open]);
  const icon = (slug: string | null) =>
    slug ? (
      <ModelIconImg
        model={slug}
        provider={kind === "provider" ? slug : undefined}
        icon={kind === "icon" ? slug : undefined}
        size={18}
      />
    ) : (
      <span
        aria-hidden="true"
        className="flex size-[18px] shrink-0 items-center justify-center rounded-full bg-[var(--theme-bg-subtle)] text-10 text-theme-text-muted"
      >
        ?
      </span>
    );
  const select = (slug: string) => {
    onChange(slug);
    close();
  };
  return (
    <div ref={containerRef} className={className}>
      <PickerTrigger
        open={open}
        selected={!!selected}
        aria-label={ariaLabel}
        aria-describedby={valueId}
        onClick={() => setOpen(!open)}
      >
        {icon(selected)}
        <span id={valueId} className="truncate">
          {selected ? label(selected) : placeholder}
        </span>
      </PickerTrigger>
      {open &&
        createPortal(
          <div
            ref={popupRef}
            style={popupStyle}
            className="ui-select-dropdown flex flex-col overflow-hidden"
            onKeyDown={(event) => {
              const choices = Array.from(
                event.currentTarget.querySelectorAll<HTMLButtonElement>(
                  '[role="option"]',
                ),
              );
              if (event.key === "Escape") {
                event.preventDefault();
                event.stopPropagation();
                close();
              } else if (event.key === "Tab") {
                const controls = [searchRef.current, ...choices].filter(
                  Boolean,
                );
                if (
                  document.activeElement ===
                  (event.shiftKey ? controls[0] : controls.at(-1))
                ) {
                  event.stopPropagation();
                  close();
                }
              } else if (
                ["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key) &&
                (event.target !== searchRef.current ||
                  event.key.startsWith("Arrow"))
              ) {
                event.preventDefault();
                event.stopPropagation();
                const current = choices.indexOf(
                  document.activeElement as HTMLButtonElement,
                );
                const next =
                  event.key === "Home"
                    ? 0
                    : event.key === "End"
                      ? choices.length - 1
                      : current < 0
                        ? event.key === "ArrowDown"
                          ? 0
                          : choices.length - 1
                        : (current +
                            (event.key === "ArrowDown" ? 1 : -1) +
                            choices.length) %
                          choices.length;
                choices[next]?.focus();
              }
            }}
          >
            <PanelSearchInput
              as={Input}
              ref={searchRef}
              value={search}
              onValueChange={setSearch}
              aria-label={t("common.search")}
              placeholder={t("common.search")}
              className="!min-h-11 shrink-0"
            />
            <div
              role="listbox"
              aria-label={ariaLabel}
              className="min-h-0 flex-1 overflow-y-auto overscroll-contain"
            >
              <button
                type="button"
                role="option"
                aria-selected={!value}
                className="ui-select-option min-h-11 sm:min-h-9"
                onClick={() => select("")}
              >
                {icon(null)}
                <span className="ui-select-option__label">{placeholder}</span>
              </button>
              {loading ? (
                <p role="status" className="p-3 text-12 text-theme-text-muted">
                  {t("common.loading")}
                </p>
              ) : (
                filtered.map((slug) => (
                  <button
                    key={slug}
                    type="button"
                    role="option"
                    aria-selected={value === slug}
                    className={`ui-select-option min-h-11 sm:min-h-9 ${value === slug ? "ui-select-option--active" : ""}`}
                    onClick={() => select(slug)}
                  >
                    {icon(slug)}
                    <span className="ui-select-option__label">
                      {label(slug)}
                    </span>
                    <span className="ml-auto truncate text-10 text-theme-text-muted">
                      {slug}
                    </span>
                  </button>
                ))
              )}
              {!loading && !filtered.length && (
                <p className="p-3 text-12 text-theme-text-muted">
                  {t(
                    kind === "provider"
                      ? "agentConfig.noProviders"
                      : "agentConfig.noModelIcons",
                  )}
                </p>
              )}
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}
