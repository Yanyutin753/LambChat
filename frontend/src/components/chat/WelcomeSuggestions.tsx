import type { ReactNode } from "react";
import { Sparkles } from "lucide-react";
import { getWelcomeSuggestionButtonClass } from "./welcomeLayout";

export function WelcomeSuggestions({
  suggestions,
  onSelect,
  disabled = false,
}: {
  suggestions: ReadonlyArray<{ text: string; icon?: ReactNode }>;
  onSelect: (text: string) => void;
  disabled?: boolean;
}) {
  return (
    <div className="welcome-suggestions-grid grid grid-cols-1 sm:grid-cols-2 gap-2 sm:gap-2.5 md:gap-2.5 xl:gap-3 2xl:gap-3">
      {suggestions.map((suggestion, i) => (
        <button
          key={suggestion.text}
          type="button"
          disabled={disabled}
          title={suggestion.text}
          onClick={() => onSelect(suggestion.text)}
          className={
            getWelcomeSuggestionButtonClass(i) +
            " disabled:cursor-not-allowed disabled:opacity-50"
          }
          style={{
            backgroundColor: "var(--theme-bg-card)",
            borderColor: "var(--theme-border)",
            animationDelay: `${i * 60}ms`,
          }}
        >
          {/* Hover shimmer layer */}
          <span className="welcome-card-shimmer" aria-hidden="true" />
          <span
            className="relative flex items-center justify-center size-6 sm:size-7 xl:size-8 2xl:size-8 rounded-lg text-13 sm:text-15 xl:text-18 2xl:text-18 shrink-0 transition-transform duration-300 group-hover:scale-110"
            style={{
              backgroundColor: "var(--theme-primary-light)",
              color: "var(--theme-primary)",
            }}
          >
            {suggestion.icon || <Sparkles size={16} />}
          </span>
          <span
            className="relative text-12.5 sm:text-13.5 leading-[1.4] sm:leading-[1.45] truncate transition-colors duration-300 group-hover:text-[var(--theme-text)]"
            style={{ color: "var(--theme-text-secondary)" }}
          >
            {suggestion.text}
          </span>
        </button>
      ))}
    </div>
  );
}
