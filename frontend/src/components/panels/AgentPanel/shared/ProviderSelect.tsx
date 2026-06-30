import React, { useState, useRef, useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Search } from "lucide-react";
import { Input, PickerTrigger } from "../../../common";
import { PanelSearchInput } from "../../../common/PanelSearchInput";
import { ModelIconImg } from "../../../agent/modelIcon.tsx";
import { modelApi } from "../../../../services/api/model";
import { PROVIDER_LABELS } from "./providerLabels";

interface ProviderSelectProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
}

export const ProviderSelect = React.memo(function ProviderSelect({
  value,
  onChange,
  placeholder = "",
  className = "",
}: ProviderSelectProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [providers, setProviders] = useState<string[]>([]);
  const [loaded, setLoaded] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  // 从后端拉取 provider 列表（只拉一次）
  useEffect(() => {
    modelApi
      .listProviders()
      .then((list) => {
        setProviders(list.map((p) => p.value));
        setLoaded(true);
      })
      .catch(() => {
        // fallback: 用 PROVIDER_LABELS 里的 key
        setProviders(Object.keys(PROVIDER_LABELS));
        setLoaded(true);
      });
  }, []);

  const label = (slug: string) => PROVIDER_LABELS[slug] || slug;

  const selected = providers.includes(value) ? value : null;

  const filtered = useMemo(() => {
    if (!search.trim()) return providers;
    const q = search.toLowerCase();
    return providers.filter(
      (slug) => slug.includes(q) || label(slug).toLowerCase().includes(q),
    );
  }, [search, providers]);

  useEffect(() => {
    if (!open) return;
    const handleClick = (e: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
        setSearch("");
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  useEffect(() => {
    if (open && searchRef.current) {
      searchRef.current.focus();
    }
  }, [open]);

  const handleSelect = (v: string) => {
    onChange(v);
    setOpen(false);
    setSearch("");
  };

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      {/* Trigger */}
      <PickerTrigger
        onClick={() => setOpen(!open)}
        open={open}
        selected={!!selected}
      >
        {selected ? (
          <ModelIconImg model={selected} provider={selected} size={18} />
        ) : (
          <div className="w-[18px] h-[18px] flex items-center justify-center rounded-full bg-stone-200 dark:bg-stone-600">
            <span className="text-[10px] font-bold text-stone-500 dark:text-stone-300">
              ?
            </span>
          </div>
        )}
        <span className="truncate">
          {selected ? label(selected) : placeholder}
        </span>
      </PickerTrigger>

      {/* Dropdown */}
      {open && (
        <div className="absolute left-0 top-full z-50 mt-1.5 w-full rounded-xl bg-white dark:bg-stone-800 shadow-lg border border-[var(--glass-border)] overflow-hidden animate-in fade-in-0 zoom-in-95 duration-150">
          {/* Search input */}
          <div className="px-3 pt-2.5 pb-2">
            <PanelSearchInput
              as={Input}
              ref={searchRef}
              type="text"
              value={search}
              onValueChange={setSearch}
              placeholder={t("common.search", "搜索...")}
              leadingIcon={<Search size={14} />}
              className="py-1.5 text-sm"
            />
          </div>

          {/* Provider list */}
          <div className="max-h-52 overflow-y-auto overscroll-contain">
            {/* "Auto detect" option */}
            <button
              type="button"
              onClick={() => handleSelect("")}
              className={`w-full flex items-center gap-2.5 px-3.5 py-2 text-sm text-left hover:bg-stone-100/80 dark:hover:bg-stone-700/50 transition-colors ${
                !value ? "bg-stone-50 dark:bg-stone-700/30" : ""
              }`}
            >
              <div className="w-[18px] h-[18px] flex items-center justify-center rounded-full bg-stone-200 dark:bg-stone-600 shrink-0">
                <span className="text-[10px] font-bold text-stone-500 dark:text-stone-300">
                  ?
                </span>
              </div>
              <span className="text-stone-500 dark:text-stone-400">
                {placeholder}
              </span>
            </button>

            {loaded ? (
              filtered.map((slug) => (
                <button
                  key={slug}
                  type="button"
                  onClick={() => handleSelect(slug)}
                  className={`w-full flex items-center gap-2.5 px-3.5 py-2 text-sm text-left hover:bg-stone-100/80 dark:hover:bg-stone-700/50 transition-colors ${
                    value === slug ? "bg-stone-50 dark:bg-stone-700/30" : ""
                  }`}
                >
                  <ModelIconImg model={slug} provider={slug} size={18} />
                  <span className="text-stone-700 dark:text-stone-200">
                    {label(slug)}
                  </span>
                  <span className="text-xs text-stone-400 dark:text-stone-500 ml-auto font-mono">
                    {slug}
                  </span>
                </button>
              ))
            ) : (
              <div className="px-3.5 py-4 text-sm text-stone-400 text-center">
                {t("common.loading")}
              </div>
            )}

            {loaded && filtered.length === 0 && (
              <div className="px-3.5 py-4 text-sm text-stone-400 dark:text-stone-500 text-center">
                {t("agentConfig.noProviders")}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
});
