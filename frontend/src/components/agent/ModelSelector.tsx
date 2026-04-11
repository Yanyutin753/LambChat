import { memo, useState, useCallback, useEffect, useRef } from "react";
import { ChevronDown, Check, Info } from "lucide-react";
import { getModelIconUrl, isMonochromeIcon } from "./modelIcon";

function ModelIconImg({ model, size }: { model: string; size: number }) {
  const url = getModelIconUrl(model);
  const mono = isMonochromeIcon(model);
  if (!url) {
    return (
      <div
        className="flex items-center justify-center rounded-full bg-stone-200 dark:bg-stone-600"
        style={{ width: size, height: size }}
      >
        <span className="text-xs font-bold text-stone-600 dark:text-stone-200">
          {model.charAt(0).toUpperCase()}
        </span>
      </div>
    );
  }
  return (
    <div
      className="flex items-center justify-center rounded-full bg-white dark:bg-stone-600"
      style={{ width: size, height: size }}
    >
      <img
        src={url}
        alt={model}
        width={size * 0.7}
        height={size * 0.7}
        className={mono ? "dark:invert" : ""}
      />
    </div>
  );
}

export interface ModelOption {
  value: string;
  label: string;
  description?: string;
}

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
        <ModelIconImg model={model.value} size={22} />
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
  currentModel: string;
  onSelectModel: (modelValue: string) => void;
}

const ModelSelector = memo(function ModelSelector({
  models,
  currentModel,
  onSelectModel,
}: ModelSelectorProps) {
  const [showSelector, setShowSelector] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const currentModelInfo = models.find((m) => m.value === currentModel);

  const handleSelectModel = useCallback(
    (modelValue: string) => {
      onSelectModel(modelValue);
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
        <span className="text-base font-semibold text-stone-600 dark:text-stone-300">
          {currentModelInfo?.label || currentModel}
        </span>
        <ChevronDown
          size={16}
          className={`text-stone-400 dark:text-stone-300 transition-transform duration-200 ${
            showSelector ? "rotate-180" : ""
          }`}
        />
      </button>

      {showSelector && (
        <div className="absolute left-0 top-full z-50 mt-2 w-72 rounded-xl bg-white dark:bg-stone-800 shadow-lg border border-stone-200 dark:border-stone-700 overflow-hidden animate-in fade-in-0 zoom-in-95 duration-150">
          {models.map((model) => (
            <ModelItem
              key={model.value}
              model={model}
              isSelected={model.value === currentModel}
              onSelect={() => handleSelectModel(model.value)}
            />
          ))}
        </div>
      )}
    </div>
  );
});

export { ModelSelector };
