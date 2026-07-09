import { memo, useState, useCallback, useEffect, useRef, useMemo } from "react";
import { createPortal } from "react-dom";
import { ChevronDown, Check, Info, Pin, Eye, Star, Search } from "lucide-react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { useStickyDropdownPosition } from "../../hooks/useStickyDropdownPosition";
import { ModelIconImg } from "./modelIcon.tsx";
import { shouldCloseModelSelector } from "./modelSelectorGuards";
import type { ModelOption } from "../../services/api/model";
import { authApi } from "../../services/api";
import { PanelSearchInput } from "../common/PanelSearchInput";
import { Tooltip } from "../common/Tooltip";
import { PROVIDER_LABELS } from "../panels/AgentPanel/shared/providerLabels";

const MAX_PINNED = 10;
type ModelFilterKey = "all" | "pinned" | "vision" | `provider:${string}`;

interface ModelFilterOption {
  key: ModelFilterKey;
  label: string;
  count: number;
}

function getProviderLabel(provider: string): string {
  return PROVIDER_LABELS[provider] ?? provider;
}

function modelMatchesSearch(model: ModelOption, query: string): boolean {
  if (!query) return true;
  const haystack = [model.label, model.value, model.provider, model.description]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();

  return haystack.includes(query);
}

interface ModelItemProps {
  model: ModelOption;
  isSelected: boolean;
  isPinned: boolean;
  isDefault: boolean;
  onSelect: () => void;
  onTogglePin: () => void;
  onSetDefault: () => void;
  canPin: boolean;
}

const ModelItem = memo(function ModelItem({
  model,
  isSelected,
  isPinned,
  isDefault,
  onSelect,
  onTogglePin,
  onSetDefault,
  canPin,
}: ModelItemProps) {
  const { t } = useTranslation();
  const [showTip, setShowTip] = useState(false);
  const tipTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const iconRef = useRef<HTMLSpanElement>(null);

  const show = useCallback(() => {
    clearTimeout(tipTimer.current);
    setShowTip(true);
  }, []);

  const hide = useCallback(() => {
    tipTimer.current = setTimeout(() => setShowTip(false), 150);
  }, []);

  const toggle = useCallback((e: React.TouchEvent) => {
    e.stopPropagation();
    setShowTip((v) => !v);
  }, []);

  // Close tooltip when clicking outside
  useEffect(() => {
    if (!showTip) return;
    const handleClick = (e: MouseEvent) => {
      if (iconRef.current && !iconRef.current.contains(e.target as Node)) {
        setShowTip(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [showTip]);

  const tipPlacement = useRef<"top" | "bottom">("top");

  const tipStyle = (() => {
    if (!showTip || !iconRef.current) return undefined;
    const rect = iconRef.current.getBoundingClientRect();
    const estimatedHeight = Math.min(model.description!.length * 0.6, 120) + 24;
    const showAbove = rect.top > estimatedHeight + 8;
    tipPlacement.current = showAbove ? "top" : "bottom";
    if (showAbove) {
      return {
        left: rect.left + rect.width / 2,
        top: rect.top - 8,
        transform: "translate(-50%, -100%)",
      };
    }
    return {
      left: rect.left + rect.width / 2,
      top: rect.bottom + 8,
      transform: "translate(-50%, 0)",
    };
  })();

  return (
    <div className="group/model-item relative px-1 py-px">
      <div
        className={`relative flex min-h-[38px] items-center gap-2 rounded-md px-2.5 py-1.5 transition-all duration-150 ${
          isSelected
            ? "text-[var(--theme-text)]"
            : "hover:bg-stone-100/80 dark:hover:bg-stone-700/45"
        }`}
        style={
          isSelected
            ? {
                background:
                  "color-mix(in srgb, var(--theme-primary) 6%, var(--theme-bg-card))",
                boxShadow:
                  "inset 0 0 0 1px color-mix(in srgb, var(--theme-primary) 12%, transparent)",
              }
            : undefined
        }
      >
        <button
          type="button"
          onClick={onSelect}
          aria-current={isSelected ? "true" : undefined}
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
        >
          <ModelIconImg
            model={model.value}
            provider={model.provider}
            icon={model.icon}
            size={20}
          />
          <div className="flex items-center gap-1.5 flex-1 min-w-0">
            <span
              className={`truncate text-[13px] leading-5 ${
                isSelected
                  ? "text-[var(--theme-text)]"
                  : "text-stone-700 dark:text-stone-200"
              }`}
            >
              {model.label}
            </span>
            {model.profile?.supports_vision && (
              <Tooltip content="Vision">
                <span className="inline-flex items-center shrink-0 ml-0.5">
                  <Eye
                    size={13}
                    className="text-stone-400 dark:text-stone-500"
                  />
                </span>
              </Tooltip>
            )}
            {model.description && (
              <span
                ref={iconRef}
                className="inline-flex items-center shrink-0 cursor-pointer ml-0.5"
                onMouseEnter={show}
                onMouseLeave={hide}
                onTouchStart={toggle}
              >
                <Info
                  size={13}
                  className="text-stone-400 hover:text-stone-600 dark:text-stone-500 dark:hover:text-stone-300 transition-colors"
                />
                {showTip && (
                  <span
                    className="fixed z-[60] max-w-[240px] w-max rounded-lg bg-stone-700 dark:bg-stone-900 px-2.5 py-1.5 text-xs leading-relaxed text-white shadow-lg whitespace-normal"
                    style={tipStyle}
                    onTouchStart={(e) => e.stopPropagation()}
                  >
                    {model.description}
                    {tipPlacement.current === "top" ? (
                      <span className="absolute left-1/2 -translate-x-1/2 top-full border-[5px] border-transparent border-t-stone-700 dark:border-t-stone-900" />
                    ) : (
                      <span className="absolute left-1/2 -translate-x-1/2 bottom-full border-[5px] border-transparent border-b-stone-700 dark:border-b-stone-900" />
                    )}
                  </span>
                )}
              </span>
            )}
          </div>
        </button>
        <Tooltip content={t("profile.setDefault")}>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onSetDefault();
            }}
            className="shrink-0 flex items-center justify-center w-5 h-5 rounded-md transition-opacity cursor-pointer"
          >
            <Star
              size={13}
              className={
                isDefault
                  ? "text-amber-400 dark:text-amber-500"
                  : "text-stone-400 hover:text-stone-600 dark:text-stone-500 dark:hover:text-stone-300"
              }
              fill={isDefault ? "currentColor" : "none"}
            />
          </button>
        </Tooltip>
        <Tooltip
          content={
            isPinned
              ? t("profile.unpinModel")
              : canPin
                ? t("profile.pinModel")
                : t("profile.maxPinnedModels", { max: MAX_PINNED })
          }
        >
          <button
            type="button"
            onClick={() => {
              if (canPin || isPinned) onTogglePin();
            }}
            className={`shrink-0 flex items-center justify-center w-5 h-5 rounded-md transition-opacity ${
              !canPin && !isPinned ? "cursor-not-allowed" : "cursor-pointer"
            }`}
          >
            <Pin
              size={13}
              className={
                isPinned
                  ? "text-stone-500 dark:text-stone-400"
                  : canPin
                    ? "text-stone-400 hover:text-stone-600 dark:text-stone-500 dark:hover:text-stone-300"
                    : "text-stone-300 dark:text-stone-600"
              }
              fill={isPinned ? "currentColor" : "none"}
            />
          </button>
        </Tooltip>
        <span
          className={`shrink-0 flex items-center justify-center w-5 h-5 rounded-full transition-all duration-150 ${
            isSelected ? "opacity-100" : "opacity-0"
          }`}
          style={
            isSelected
              ? {
                  background:
                    "color-mix(in srgb, var(--theme-primary) 12%, transparent)",
                }
              : undefined
          }
          aria-hidden="true"
        >
          <Check
            size={12}
            className="text-[var(--theme-primary)]"
            strokeWidth={2.4}
          />
        </span>
      </div>
    </div>
  );
});

interface ModelSelectorProps {
  models: ModelOption[];
  currentModelId: string;
  pinnedModelIds?: string[];
  onTogglePinnedModel?: (modelId: string) => void;
  onSelectModel: (modelId: string, modelValue: string) => void;
}

const ModelSelector = memo(function ModelSelector({
  models,
  currentModelId,
  pinnedModelIds = [],
  onTogglePinnedModel,
  onSelectModel,
}: ModelSelectorProps) {
  const { t } = useTranslation();
  const [showSelector, setShowSelector] = useState(false);
  const [activeFilter, setActiveFilter] = useState<ModelFilterKey>("all");
  const [modelSearch, setModelSearch] = useState("");
  const [defaultTick, setDefaultTick] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const currentModelInfo = models.find((m) => m.id === currentModelId);

  const handleSetDefault = useCallback(
    (modelId: string, modelValue: string) => {
      localStorage.setItem("defaultModelId", modelId);
      localStorage.setItem("defaultModel", modelValue);
      authApi
        .updateMetadata({ defaultModel: modelValue, defaultModelId: modelId })
        .catch(() => {});
      window.dispatchEvent(
        new CustomEvent("model-preference-updated", {
          detail: { modelId, modelValue },
        }),
      );
      setDefaultTick((t) => t + 1);
      toast.success(t("profile.defaultModelSet"));
    },
    [t],
  );

  useEffect(() => {
    const handler = () => setDefaultTick((t) => t + 1);
    window.addEventListener("model-preference-updated", handler);
    return () =>
      window.removeEventListener("model-preference-updated", handler);
  }, []);

  const handleSelectModel = useCallback(
    (modelId: string, modelValue: string) => {
      onSelectModel(modelId, modelValue);
      setShowSelector(false);
    },
    [onSelectModel],
  );

  const toggleSelector = useCallback(() => {
    setShowSelector((prev) => !prev);
  }, []);

  useEffect(() => {
    if (!showSelector) return;

    const handleClickOutside = (event: MouseEvent) => {
      if (
        shouldCloseModelSelector(
          event.target as Node | null,
          containerRef.current,
          dropdownRef.current,
        )
      ) {
        setShowSelector(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [showSelector]);

  const dropdownStyle = useStickyDropdownPosition(
    containerRef,
    showSelector,
    (rect) => {
      const dropdownWidth = Math.min(384, window.innerWidth - 12);
      return {
        position: "fixed",
        top: rect.bottom + 6,
        left: Math.min(
          Math.max(rect.left, 6),
          window.innerWidth - dropdownWidth - 6,
        ),
      };
    },
  );

  const pinnedSet = useMemo(() => new Set(pinnedModelIds), [pinnedModelIds]);

  const filterOptions = useMemo<ModelFilterOption[]>(() => {
    const providers = new Map<string, number>();
    let visionCount = 0;

    models.forEach((model) => {
      if (model.profile?.supports_vision) visionCount += 1;
      if (model.provider) {
        providers.set(model.provider, (providers.get(model.provider) ?? 0) + 1);
      }
    });

    return [
      {
        key: "all" as const,
        label: t("common.all", "全部"),
        count: models.length,
      },
      ...(pinnedModelIds.length > 0
        ? [
            {
              key: "pinned" as const,
              label: t("profile.pinned", "已置顶"),
              count: pinnedModelIds.length,
            },
          ]
        : []),
      ...(visionCount > 0
        ? [
            {
              key: "vision" as const,
              label: "Vision",
              count: visionCount,
            },
          ]
        : []),
      ...Array.from(providers.entries()).map(([provider, count]) => ({
        key: `provider:${provider}` as const,
        label: getProviderLabel(provider),
        count,
      })),
    ];
  }, [models, pinnedModelIds.length, t]);

  const filteredModels = useMemo(() => {
    const searchQuery = modelSearch.trim().toLowerCase();

    return models.filter((model) => {
      const matchesFilter =
        activeFilter === "all" ||
        (activeFilter === "pinned" && pinnedSet.has(model.id)) ||
        (activeFilter === "vision" && model.profile?.supports_vision) ||
        (activeFilter.startsWith("provider:") &&
          model.provider === activeFilter.slice("provider:".length));

      return matchesFilter && modelMatchesSearch(model, searchQuery);
    });
  }, [activeFilter, modelSearch, models, pinnedSet]);

  // Sort models: pinned first (in pinned order), then unpinned (original order)
  const sortedModels = useMemo(() => {
    const pinned = filteredModels.filter((m) => pinnedSet.has(m.id));
    const pinnedOrdered = pinned.sort(
      (a, b) => pinnedModelIds.indexOf(a.id) - pinnedModelIds.indexOf(b.id),
    );
    const unpinned = filteredModels.filter((m) => !pinnedSet.has(m.id));
    return { pinned: pinnedOrdered, unpinned };
  }, [filteredModels, pinnedModelIds, pinnedSet]);

  const isModelDefault = useCallback(
    (modelId: string) => {
      void defaultTick;
      return localStorage.getItem("defaultModelId") === modelId;
    },
    [defaultTick],
  );

  if (models.length === 0) return null;

  return (
    <div
      ref={containerRef}
      className="relative"
      onClick={(e) => e.stopPropagation()}
    >
      <button
        onClick={toggleSelector}
        className="flex items-center gap-1.5 text-stone-600 hover:opacity-70 dark:text-stone-300 transition-opacity"
      >
        <span className="text-base font-semibold max-w-[200px] truncate">
          {currentModelInfo?.label || currentModelId}
        </span>
        <ChevronDown
          size={14}
          className={`transition-transform duration-200 ${
            showSelector ? "rotate-180" : ""
          }`}
        />
      </button>

      {showSelector &&
        createPortal(
          <div
            ref={dropdownRef}
            className="fixed z-[10000] w-[min(calc(100vw-0.75rem),24rem)] rounded-lg bg-white dark:bg-stone-800 shadow-[0_14px_36px_-22px_rgba(0,0,0,0.45)] border border-stone-200 dark:border-stone-700 overflow-hidden animate-scale-in"
            style={dropdownStyle}
          >
            <div className="px-3 pt-2 pb-1.5">
              <div
                className="flex gap-1.5 overflow-x-auto whitespace-nowrap py-0.5 -my-0.5 overscroll-x-contain"
                style={{ scrollbarWidth: "none" }}
              >
                {filterOptions.map((option) => {
                  const selected = option.key === activeFilter;
                  return (
                    <button
                      key={option.key}
                      type="button"
                      onClick={() => setActiveFilter(option.key)}
                      aria-pressed={selected}
                      className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium leading-5 transition-colors ${
                        selected
                          ? "bg-stone-800 text-white dark:bg-stone-100 dark:text-stone-900"
                          : "bg-stone-100 text-stone-600 hover:bg-stone-200 dark:bg-stone-700/60 dark:text-stone-300 dark:hover:bg-stone-700"
                      }`}
                    >
                      {option.label}
                      <span
                        className={`ml-1 ${
                          selected
                            ? "text-white/70 dark:text-stone-900/60"
                            : "text-stone-400 dark:text-stone-500"
                        }`}
                      >
                        {option.count}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="border-t border-stone-100 dark:border-stone-700/70 px-3 py-2">
              <div className="flex items-center gap-2 text-stone-400 dark:text-stone-500">
                <Search size={14} strokeWidth={2.2} className="shrink-0" />
                <PanelSearchInput
                  value={modelSearch}
                  onValueChange={setModelSearch}
                  placeholder={t("profile.searchModels", "搜索模型")}
                  autoComplete="off"
                  className="min-w-0 flex-1 bg-transparent text-[13px] leading-5 text-stone-700 outline-none placeholder:text-stone-400 dark:text-stone-100 dark:placeholder:text-stone-500"
                />
              </div>
            </div>

            <div className="border-t border-stone-100 dark:border-stone-700/70">
              <div className="max-h-72 overflow-y-auto overscroll-contain py-1">
                {filteredModels.length === 0 ? (
                  <div className="px-3 py-6 text-center text-[13px] text-stone-400 dark:text-stone-500">
                    {t("common.noSearchResults", "没有找到匹配结果")}
                  </div>
                ) : (
                  <>
                    {sortedModels.pinned.map((model) => (
                      <ModelItem
                        key={model.id}
                        model={model}
                        isSelected={model.id === currentModelId}
                        isPinned={true}
                        isDefault={isModelDefault(model.id)}
                        onSelect={() =>
                          handleSelectModel(model.id, model.value)
                        }
                        onTogglePin={() => onTogglePinnedModel?.(model.id)}
                        onSetDefault={() =>
                          handleSetDefault(model.id, model.value)
                        }
                        canPin={true}
                      />
                    ))}
                    {sortedModels.unpinned.map((model) => (
                      <ModelItem
                        key={model.id}
                        model={model}
                        isSelected={model.id === currentModelId}
                        isPinned={false}
                        isDefault={isModelDefault(model.id)}
                        onSelect={() =>
                          handleSelectModel(model.id, model.value)
                        }
                        onTogglePin={() => onTogglePinnedModel?.(model.id)}
                        onSetDefault={() =>
                          handleSetDefault(model.id, model.value)
                        }
                        canPin={pinnedModelIds.length < MAX_PINNED}
                      />
                    ))}
                  </>
                )}
              </div>
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
});

export { ModelSelector };
