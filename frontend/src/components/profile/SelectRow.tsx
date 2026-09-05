import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { ChevronRight, Check } from "lucide-react";
import { SkeletonLine } from "../skeletons";

/** Reusable selection row — opens a centered dialog popup */
export function SelectRow<T extends string>({
  label,
  value,
  options,
  open,
  onToggle,
  onSelect,
  loading,
  renderLabel,
}: {
  label: string;
  value: T;
  options: readonly { key: T; labelKey: string }[];
  open: boolean;
  onToggle: () => void;
  onSelect: (key: T) => void;
  loading?: boolean;
  renderLabel?: (key: T) => string;
}) {
  const { t } = useTranslation();
  const selected = options.find((o) => o.key === value);

  return (
    <>
      <button
        onClick={onToggle}
        className="flex w-full items-center justify-between py-3 first:pt-0 last:pb-0 text-left"
      >
        <span className="text-sm text-stone-700 dark:text-stone-200">
          {label}
        </span>
        <span className="flex items-center gap-1 text-xs text-stone-500 dark:text-stone-400">
          {loading ? (
            <SkeletonLine width="w-16" />
          ) : (
            <span className="truncate max-w-[140px]">
              {renderLabel
                ? renderLabel(value)
                : selected
                  ? t(selected.labelKey)
                  : value}
            </span>
          )}
          <ChevronRight size={14} className="shrink-0 text-stone-400" />
        </span>
      </button>
      {open &&
        createPortal(
          <div
            className="safe-area-viewport-padding fixed inset-0 z-[300] flex items-center justify-center animate-fade-in"
            onClick={onToggle}
          >
            <div className="absolute inset-0 bg-black/40" />
            <div
              className="relative z-10 w-[300px] max-h-[60dvh] rounded-2xl bg-theme-bg-card dark:bg-stone-800 border border-stone-200 dark:border-stone-700 shadow-2xl overflow-hidden animate-scale-in"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="px-5 pt-4 pb-2">
                <h4 className="text-sm font-semibold font-serif text-stone-900 dark:text-stone-100">
                  {label}
                </h4>
              </div>
              <div className="overflow-y-auto max-h-[50dvh] pb-2">
                {options.map((opt) => (
                  <button
                    key={opt.key}
                    onClick={() => onSelect(opt.key)}
                    className={`w-full text-left px-5 py-2.5 text-sm transition-colors ${
                      value === opt.key
                        ? "bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-300 font-medium"
                        : "text-stone-700 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-700/50"
                    }`}
                  >
                    <span className="flex items-center justify-between">
                      {renderLabel ? renderLabel(opt.key) : t(opt.labelKey)}
                      {value === opt.key && (
                        <Check size={14} className="text-amber-500 shrink-0" />
                      )}
                    </span>
                  </button>
                ))}
              </div>
              <div className="border-t border-stone-100 dark:border-stone-700/50 px-5 py-3">
                <button
                  onClick={onToggle}
                  className="w-full text-center text-xs font-medium text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-200 transition-colors"
                >
                  {t("common.cancel")}
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
