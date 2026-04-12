import { memo, useState, useCallback, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { ChevronDown, Check, Info } from "lucide-react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { ModelIconImg } from "./modelIcon.tsx";
import type { ModelOption } from "../../services/api/model";

interface ModelItemProps {
  model: ModelOption;
  isSelected: boolean;
  onSelect: () => void;
}

const ModelItem = memo(function ModelItem({
  model,
  isSelected,
  onSelect,
}: ModelItemProps) {
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

  const tipStyle = (() => {
    if (!showTip || !iconRef.current) return undefined;
    const rect = iconRef.current.getBoundingClientRect();
    return {
      left: rect.left + rect.width / 2,
      top: rect.top - 8,
      transform: "translate(-50%, -100%)",
    };
  })();

  return (
    <button
      onClick={onSelect}
      className="w-full px-3 py-2.5 text-left hover:bg-stone-100/80 dark:hover:bg-stone-700/50 transition-colors"
    >
      <div className="flex items-center gap-2.5">
        <ModelIconImg model={model.value} provider={model.provider} size={22} />
        <div className="flex items-center gap-1 flex-1 min-w-0">
          <span className="text-sm text-stone-700 dark:text-stone-200 truncate">
            {model.label}
          </span>
          {model.description && (
            <span
              ref={iconRef}
              className="inline-flex items-center shrink-0 cursor-pointer ml-0.5"
              onMouseEnter={show}
              onMouseLeave={hide}
              onTouchStart={toggle}
            >
              <Info
                size={14}
                className="text-stone-400 hover:text-stone-600 dark:text-stone-500 dark:hover:text-stone-300 transition-colors"
              />
              {showTip && (
                <span
                  className="fixed z-[60] max-w-[240px] w-max rounded-lg bg-stone-700 dark:bg-stone-900 px-2.5 py-1.5 text-xs leading-relaxed text-white shadow-lg whitespace-normal"
                  style={tipStyle}
                  onTouchStart={(e) => e.stopPropagation()}
                >
                  {model.description}
                  <span className="absolute left-1/2 -translate-x-1/2 top-full border-[5px] border-transparent border-t-stone-700 dark:border-t-stone-900" />
                </span>
              )}
            </span>
          )}
        </div>
        {isSelected && (
          <Check size={16} className="text-stone-500 dark:text-stone-400" />
        )}
      </div>
    </button>
  );
});

interface ModelSelectorProps {
  models: ModelOption[];
  currentModelId: string;
  onSelectModel: (modelId: string, modelValue: string) => void;
}

const ModelSelector = memo(function ModelSelector({
  models,
  currentModelId,
  onSelectModel,
}: ModelSelectorProps) {
  const { t } = useTranslation();
  const [showSelector, setShowSelector] = useState(false);
  const [defaultTick, setDefaultTick] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  const currentModelInfo = models.find((m) => m.id === currentModelId);

  const isDefault = (() => {
    // eslint-disable-next-line react-hooks/rules-of-hooks
    void defaultTick; // re-read localStorage on tick change
    return localStorage.getItem("defaultModelId") === currentModelId;
  })();

  const handleSetDefault = useCallback(() => {
    if (!currentModelInfo) return;
    localStorage.setItem("defaultModelId", currentModelId);
    localStorage.setItem("defaultModel", currentModelInfo.value);
    window.dispatchEvent(
      new CustomEvent("model-preference-updated", {
        detail: { modelId: currentModelId, modelValue: currentModelInfo.value },
      }),
    );
    setDefaultTick((t) => t + 1);
    toast.success(t("profile.defaultModelSet"));
  }, [currentModelId, currentModelInfo]);

  // Re-render when default model changes externally (e.g. from profile)
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
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setShowSelector(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [showSelector]);

  const dropdownStyle = (() => {
    if (!showSelector || !containerRef.current) return undefined;
    const rect = containerRef.current.getBoundingClientRect();
    return {
      top: rect.bottom + 8,
      left: rect.left,
    };
  })();

  if (models.length === 0) return null;

  return (
    <div
      ref={containerRef}
      className="relative"
      onClick={(e) => e.stopPropagation()}
    >
      <button
        onClick={toggleSelector}
        className="flex items-center gap-1.5 hover:opacity-70 transition-opacity"
      >
        <span className="text-base font-semibold text-stone-600 dark:text-stone-300 max-w-[200px] truncate">
          {currentModelInfo?.label || currentModelId}
        </span>
        <ChevronDown
          size={16}
          className={`text-stone-400 dark:text-stone-300 transition-transform duration-200 ${
            showSelector ? "rotate-180" : ""
          }`}
        />
      </button>

      {!isDefault && (
        <button
          onClick={handleSetDefault}
          className="absolute left-[1px] top-full mt-[1px] text-[0.7rem] text-stone-400 hover:text-stone-600 dark:text-stone-500 dark:hover:text-stone-300 transition-colors cursor-pointer select-none"
        >
          {t("profile.setDefault")}
        </button>
      )}

      {showSelector &&
        createPortal(
          <>
            <div
              style={{
                position: "fixed",
                inset: 0,
                zIndex: 300,
                backgroundColor: "rgba(0, 0, 0, 0.5)",
              }}
              onClick={() => setShowSelector(false)}
            />
            <div
              className="fixed z-[301] w-72 max-h-80 rounded-xl bg-white dark:bg-stone-800 shadow-lg border border-stone-200 dark:border-stone-700 overflow-hidden animate-scale-in"
              style={dropdownStyle}
            >
              <div className="overflow-y-auto overscroll-contain max-h-full">
                {models.map((model) => (
                  <ModelItem
                    key={model.id}
                    model={model}
                    isSelected={model.id === currentModelId}
                    onSelect={() => handleSelectModel(model.id, model.value)}
                  />
                ))}
              </div>
            </div>
          </>,
          document.body,
        )}
    </div>
  );
});

export { ModelSelector };
