import { useTranslation } from "react-i18next";
import { ArrowUpIcon, ArrowDownIcon } from "./Icons";

interface ScrollButtonsProps {
  showTop: boolean;
  showBottom: boolean;
  onScrollToTop: () => void;
  onScrollToBottom: () => void;
}

export function ScrollButtons({
  showTop,
  showBottom,
  onScrollToTop,
  onScrollToBottom,
}: ScrollButtonsProps) {
  const { t } = useTranslation();

  return (
    <div className="fixed bottom-5 right-5 sm:bottom-6 sm:right-6 z-40 flex flex-col gap-2">
      <button
        type="button"
        disabled={!showTop}
        aria-hidden={!showTop}
        onClick={onScrollToTop}
        className={`landing-scroll-btn w-11 h-11 sm:w-10 sm:h-10 rounded-xl bg-white/90 dark:bg-stone-800/90 border border-stone-200/60 dark:border-stone-700/40 shadow-lg shadow-stone-200/30 dark:shadow-stone-900/40 flex items-center justify-center text-theme-text-secondary dark:text-theme-text-secondary hover:text-theme-text-secondary dark:hover:text-stone-200 hover:bg-white dark:hover:bg-stone-700 hover:shadow-xl hover:-translate-y-0.5 transition-all duration-300 ${
          showTop
            ? "opacity-100 pointer-events-auto"
            : "opacity-0 pointer-events-none"
        }`}
        aria-label={t("common.scrollToTop")}
      >
        <ArrowUpIcon />
      </button>
      <button
        type="button"
        disabled={!showBottom}
        aria-hidden={!showBottom}
        onClick={onScrollToBottom}
        className={`landing-scroll-btn w-11 h-11 sm:w-10 sm:h-10 rounded-xl bg-white/90 dark:bg-stone-800/90 border border-stone-200/60 dark:border-stone-700/40 shadow-lg shadow-stone-200/30 dark:shadow-stone-900/40 flex items-center justify-center text-theme-text-secondary dark:text-theme-text-secondary hover:text-theme-text-secondary dark:hover:text-stone-200 hover:bg-white dark:hover:bg-stone-700 hover:shadow-xl hover:-translate-y-0.5 transition-all duration-300 ${
          showBottom
            ? "opacity-100 pointer-events-auto"
            : "opacity-0 pointer-events-none"
        }`}
        aria-label={t("common.scrollToBottom")}
      >
        <ArrowDownIcon />
      </button>
    </div>
  );
}
