import { memo, useEffect, useMemo, useRef, useState } from "react";
import { Bot, Check, ChevronDown, Search, Sparkles } from "lucide-react";
import Fuse from "fuse.js";
import { useTranslation } from "react-i18next";

import { useAssistants } from "../../hooks/useAssistants";
import type { Assistant, AssistantSelection } from "../../types";
import { nameToAccentColor } from "./gradientUtils";
import { ASSISTANT_CATEGORIES, getCategoryById } from "./categories";

interface AssistantSelectorProps {
  currentAssistantId: string;
  currentAssistantName: string;
  onSelectAssistant: (selection: AssistantSelection) => void;
}

export const AssistantSelector = memo(function AssistantSelector({
  currentAssistantId,
  currentAssistantName,
  onSelectAssistant,
}: AssistantSelectorProps) {
  const { t } = useTranslation();
  const { assistants, isLoading } = useAssistants({ scope: "all" });
  const [isOpen, setIsOpen] = useState(false);
  const [dropdownSearch, setDropdownSearch] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const fuseRef = useRef(
    new Fuse<Assistant>([], {
      keys: ["name", "description", "tags"],
      threshold: 0.4,
    }),
  );

  const currentAssistant = useMemo(
    () =>
      assistants.find(
        (assistant) => assistant.assistant_id === currentAssistantId,
      ),
    [assistants, currentAssistantId],
  );

  const filteredAssistants = useMemo(() => {
    let filtered = assistants.filter(
      (a) => a.scope !== "public" || a.is_active,
    );
    if (selectedCategory) {
      filtered = filtered.filter((a) => a.category === selectedCategory);
    }
    if (dropdownSearch.trim()) {
      fuseRef.current.setCollection(filtered);
      filtered = fuseRef.current
        .search(dropdownSearch.trim())
        .map((r) => r.item);
    }
    return filtered;
  }, [assistants, selectedCategory, dropdownSearch]);

  const groupedByCategory = useMemo(() => {
    const groups = new Map<string, typeof filteredAssistants>();
    for (const assistant of filteredAssistants) {
      const catId = assistant.category ?? "general";
      if (!groups.has(catId)) {
        groups.set(catId, []);
      }
      groups.get(catId)!.push(assistant);
    }
    // Sort groups to match ASSISTANT_CATEGORIES order, unknown categories last
    const orderedCategoryIds = ASSISTANT_CATEGORIES.map((c) => c.id);
    const sorted: [string, typeof filteredAssistants][] = [];
    for (const catId of orderedCategoryIds) {
      const items = groups.get(catId);
      if (items && items.length > 0) {
        sorted.push([catId, items]);
      }
    }
    // Append any unknown categories
    for (const [catId, items] of groups) {
      if (!orderedCategoryIds.includes(catId)) {
        sorted.push([catId, items]);
      }
    }
    return sorted;
  }, [filteredAssistants]);

  // Focus search input when dropdown opens
  useEffect(() => {
    if (isOpen && searchInputRef.current) {
      searchInputRef.current.focus();
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;

    const handleOutsideClick = (event: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        handleClose();
      }
    };

    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, [isOpen]);

  const handleClose = () => {
    setIsOpen(false);
    setDropdownSearch("");
    setSelectedCategory(null);
  };

  const handleSelect = (assistant: (typeof assistants)[number]) => {
    onSelectAssistant({
      assistantId: assistant.assistant_id,
      assistantName: assistant.name,
      assistantPromptSnapshot: assistant.system_prompt,
      avatarUrl: assistant.avatar_url,
    });
    handleClose();
  };

  const label =
    currentAssistantName ||
    currentAssistant?.name ||
    t("assistants.none", { defaultValue: "Default Assistant" });

  const hasAvatar = currentAssistant?.avatar_url;

  return (
    <div
      ref={containerRef}
      className="relative"
      onClick={(event) => event.stopPropagation()}
    >
      {/* Trigger button */}
      <button
        type="button"
        onClick={() => setIsOpen((open) => !open)}
        className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.06] px-2.5 py-1.5 text-sm backdrop-blur-sm transition-all duration-200 hover:border-white/20 hover:bg-white/[0.1] dark:border-stone-700/60 dark:bg-stone-800/40 dark:hover:border-stone-600 dark:hover:bg-stone-800/70"
      >
        {hasAvatar ? (
          <img
            src={currentAssistant!.avatar_url!}
            alt={label}
            className="size-5 shrink-0 rounded-full object-cover ring-1 ring-black/5 dark:ring-white/10"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = "none";
            }}
          />
        ) : (
          <Sparkles
            size={14}
            className="shrink-0 text-amber-500/90 dark:text-amber-400/80"
          />
        )}
        <span className="max-w-[160px] truncate font-medium text-stone-700 dark:text-stone-200">
          {label}
        </span>
        <ChevronDown
          size={13}
          className={`shrink-0 text-stone-400 transition-transform duration-200 dark:text-stone-500 ${
            isOpen ? "rotate-180" : ""
          }`}
        />
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute left-0 top-full z-50 mt-1.5 w-[400px] origin-top-left animate-[scale-in_0.15s_ease-out] overflow-hidden rounded-xl border border-stone-200/80 bg-white/95 shadow-xl shadow-stone-900/10 backdrop-blur-xl dark:border-stone-700/60 dark:bg-stone-900/95 dark:shadow-stone-950/40">
          {/* Search header */}
          <div className="border-b border-stone-100 px-3 py-2.5 dark:border-stone-800/60">
            <div className="relative">
              <Search
                size={14}
                className="absolute left-2.5 top-1/2 -translate-y-1/2 text-stone-400 dark:text-stone-500"
              />
              <input
                ref={searchInputRef}
                type="text"
                value={dropdownSearch}
                onChange={(e) => setDropdownSearch(e.target.value)}
                className="w-full rounded-lg border border-stone-200 bg-stone-50 py-2 pl-8 pr-3 text-[13px] text-stone-900 outline-none transition-all placeholder:text-stone-400 focus:border-stone-400 focus:bg-white focus:ring-2 focus:ring-stone-200 dark:border-stone-700 dark:bg-stone-800/80 dark:text-stone-100 dark:placeholder:text-stone-500 dark:focus:border-stone-500 dark:focus:bg-stone-800 dark:focus:ring-stone-800"
                placeholder={t("assistants.searchPlaceholder", {
                  defaultValue: "Search assistants...",
                })}
              />
            </div>

            {/* Category quick-filter pills */}
            <div className="mt-2 flex flex-wrap gap-1">
              <button
                type="button"
                onClick={() => setSelectedCategory(null)}
                className={`rounded-full px-2.5 py-1 text-[11px] font-medium transition-all duration-150 ${
                  selectedCategory === null
                    ? "bg-stone-900 text-white shadow-sm dark:bg-stone-100 dark:text-stone-900"
                    : "bg-stone-100 text-stone-500 hover:bg-stone-200 hover:text-stone-700 dark:bg-stone-800/60 dark:text-stone-400 dark:hover:bg-stone-700 dark:hover:text-stone-200"
                }`}
              >
                All
              </button>
              {ASSISTANT_CATEGORIES.map((cat) => {
                const Icon = cat.icon;
                return (
                  <button
                    key={cat.id}
                    type="button"
                    onClick={() =>
                      setSelectedCategory(
                        selectedCategory === cat.id ? null : cat.id,
                      )
                    }
                    className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-medium transition-all duration-150 ${
                      selectedCategory === cat.id
                        ? "bg-stone-900 text-white shadow-sm dark:bg-stone-100 dark:text-stone-900"
                        : "bg-stone-100 text-stone-500 hover:bg-stone-200 hover:text-stone-700 dark:bg-stone-800/60 dark:text-stone-400 dark:hover:bg-stone-700 dark:hover:text-stone-200"
                    }`}
                  >
                    <Icon size={10} strokeWidth={2} />
                    {cat.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Options list */}
          <div className="max-h-[360px] overflow-y-auto py-1">
            {/* Default option */}
            <button
              type="button"
              onClick={() => {
                onSelectAssistant({
                  assistantId: "",
                  assistantName: "",
                  assistantPromptSnapshot: "",
                });
                handleClose();
              }}
              className="flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors hover:bg-stone-50 dark:hover:bg-stone-800/40"
              style={{
                borderLeft: !currentAssistantId
                  ? "3px solid #f59e0b"
                  : "3px solid transparent",
              }}
            >
              <div className="flex size-8 items-center justify-center rounded-lg bg-stone-100 text-stone-500 dark:bg-stone-800 dark:text-stone-400">
                <Bot size={15} strokeWidth={1.8} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-[13px] font-medium text-stone-800 dark:text-stone-100">
                  {t("assistants.none", { defaultValue: "Default Assistant" })}
                </div>
                <div className="text-[11px] text-stone-400 dark:text-stone-500">
                  {t("assistants.noneDescription", {
                    defaultValue:
                      "Use the base agent prompt without an extra assistant preset.",
                  })}
                </div>
              </div>
              {!currentAssistantId && (
                <Check
                  size={15}
                  className="shrink-0 text-amber-600 dark:text-amber-400"
                />
              )}
            </button>

            {isLoading ? (
              <div className="px-4 py-8 text-center text-[13px] text-stone-400 dark:text-stone-500">
                {t("common.loading", { defaultValue: "Loading..." })}
              </div>
            ) : filteredAssistants.length === 0 ? (
              <div className="px-4 py-8 text-center text-[13px] text-stone-400 dark:text-stone-500">
                {t("assistants.noResults", {
                  defaultValue: "No results found",
                })}
              </div>
            ) : (
              groupedByCategory.map(([catId, items]) => {
                const category = getCategoryById(catId);
                return (
                  <div key={catId} className="px-3 pt-2 pb-1">
                    <p className="mb-1 px-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-stone-400 dark:text-stone-600">
                      {category?.label ?? catId}
                    </p>
                    <div className="space-y-0.5">
                      {items.map((assistant) => (
                        <button
                          key={assistant.assistant_id}
                          type="button"
                          onClick={() => handleSelect(assistant)}
                          className="flex w-full items-start gap-3 rounded-lg px-3 py-2 text-left transition-all duration-150 hover:translate-x-0.5 hover:bg-stone-50 dark:hover:bg-stone-800/40"
                          style={{
                            borderLeft:
                              assistant.assistant_id === currentAssistantId
                                ? "3px solid #f59e0b"
                                : `3px solid ${nameToAccentColor(
                                    assistant.name,
                                  )}`,
                          }}
                        >
                          <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-gradient-to-br from-amber-50 to-orange-50 text-amber-600 ring-1 ring-amber-100/50 dark:from-amber-900/30 dark:to-orange-900/20 dark:text-amber-400 dark:ring-amber-800/30">
                            {assistant.avatar_url ? (
                              <img
                                src={assistant.avatar_url}
                                alt={assistant.name}
                                className="size-full object-cover"
                                onError={(e) => {
                                  (e.target as HTMLImageElement).style.display =
                                    "none";
                                }}
                              />
                            ) : (
                              <Sparkles size={14} strokeWidth={2} />
                            )}
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-1.5">
                              <span className="truncate text-[13px] font-medium text-stone-800 dark:text-stone-100">
                                {assistant.name}
                              </span>
                              {assistant.cloned_from_assistant_id && (
                                <span className="rounded bg-stone-100 px-1.5 py-px text-[9px] font-medium uppercase tracking-wide text-stone-400 dark:bg-stone-800 dark:text-stone-500">
                                  Clone
                                </span>
                              )}
                            </div>
                            <p className="mt-0.5 line-clamp-2 text-[11px] leading-relaxed text-stone-400 dark:text-stone-500">
                              {assistant.description ||
                                assistant.tags.join(" · ")}
                            </p>
                          </div>
                          {assistant.assistant_id === currentAssistantId && (
                            <Check
                              size={15}
                              className="mt-1 shrink-0 text-amber-600 dark:text-amber-400"
                            />
                          )}
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
});
