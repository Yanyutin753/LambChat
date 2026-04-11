import { memo, useState, useCallback } from "react";
import { toast } from "react-hot-toast";
import { RefreshCw, Zap } from "lucide-react";
import { ChatInput } from "./ChatInput";
import type { ChatInputProps } from "./ChatInput";

export interface Suggestion {
  icon: string;
  text: string;
}

interface WelcomePageProps {
  greeting: string;
  subtitle: string;
  suggestionsLabel: string;
  refreshLabel: string;
  suggestions: Suggestion[] | undefined;
  canSendMessage: boolean;
  onSendMessage: (content: string) => void;
  noPermissionHint: string;
  chatInputProps: ChatInputProps;
  onRefreshSuggestions?: () => void;
}

export const WelcomePage = memo(function WelcomePage({
  greeting,
  subtitle,
  suggestionsLabel,
  refreshLabel,
  suggestions,
  canSendMessage,
  onSendMessage,
  noPermissionHint,
  chatInputProps,
  onRefreshSuggestions,
}: WelcomePageProps) {
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [animKey, setAnimKey] = useState(0);

  const handleSuggestionClick = (text: string) => {
    if (!canSendMessage) {
      toast.error(noPermissionHint);
      return;
    }
    onSendMessage(text);
  };

  const handleRefresh = useCallback(() => {
    setIsRefreshing(true);
    onRefreshSuggestions?.();
    setAnimKey((k) => k + 1);
    setTimeout(() => setIsRefreshing(false), 400);
  }, [onRefreshSuggestions]);

  return (
    <div className="welcome-root relative flex h-full flex-col items-center justify-center px-4 overflow-hidden">
      {/* Greeting section */}
      <div className="relative flex flex-col items-center mb-8 sm:mb-10 w-full max-w-[90vw]">
        {/* App icon (mobile only) */}
        <div className="sm:hidden relative mb-6">
          <img
            src="/icons/icon.svg"
            alt="LambChat"
            className="relative size-14 rounded-2xl shadow-lg ring-1 ring-stone-200/60 dark:ring-stone-700/40"
          />
        </div>

        {/* Greeting — clean sans-serif, ChatGPT style */}
        <h1
          className="welcome-greeting max-w-[90vw] text-[1.75rem] sm:text-[2rem] md:text-[2.25rem] font-semibold tracking-[-0.02em] leading-[1.2] text-center"
          style={{ color: "var(--theme-text)" }}
        >
          <img
            src="/icons/icon.svg"
            alt=""
            className="hidden sm:inline-block size-12 mr-4 align-text-bottom rounded-full"
          />
          {greeting}
        </h1>
        {/* Subtle subtitle prompt */}
        <p
          className="welcome-subtitle mt-2 sm:mt-3 text-base text-center"
          style={{ color: "var(--theme-text-secondary)" }}
        >
          {subtitle}
        </p>
      </div>

      {/* Desktop: ChatInput centered — the focal point */}
      <div className="welcome-input w-full max-w-[48rem] sm:block hidden">
        <ChatInput {...chatInputProps} />
      </div>

      {/* Desktop: Suggestions with refresh */}
      {suggestions && suggestions.length > 0 && (
        <div className="welcome-suggestions relative w-full max-w-[36rem] px-2 mt-5 sm:block hidden">
          <div className="flex items-center justify-between mb-3">
            <div
              className="flex items-center gap-1 text-sm font-medium"
              style={{ color: "var(--theme-text-secondary)" }}
            >
              <Zap size={12} />
              <span>{suggestionsLabel}</span>
            </div>
            {onRefreshSuggestions && (
              <button
                onClick={handleRefresh}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[12px] font-medium transition-colors duration-200 cursor-pointer"
                style={{
                  color: "var(--theme-text-secondary)",
                  backgroundColor: "transparent",
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLElement).style.backgroundColor =
                    "var(--theme-primary-light)";
                  (e.currentTarget as HTMLElement).style.color =
                    "var(--theme-text)";
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLElement).style.backgroundColor =
                    "transparent";
                  (e.currentTarget as HTMLElement).style.color =
                    "var(--theme-text-secondary)";
                }}
              >
                <RefreshCw
                  size={13}
                  className={isRefreshing ? "animate-spin" : ""}
                />
                <span>{refreshLabel}</span>
              </button>
            )}
          </div>
          <div key={animKey} className="grid grid-cols-2 gap-2.5">
            {suggestions.map((suggestion, i) => (
              <button
                key={suggestion.text}
                onClick={() => handleSuggestionClick(suggestion.text)}
                className="welcome-card group flex items-center gap-3 rounded-xl border px-4 py-3 text-left cursor-pointer transition-colors duration-200"
                style={{
                  backgroundColor: "var(--theme-bg-card)",
                  borderColor: "var(--theme-border)",
                  animationDelay: `${i * 60}ms`,
                }}
              >
                <span
                  className="flex items-center justify-center size-7 rounded-lg text-[15px] shrink-0"
                  style={{
                    backgroundColor: "var(--theme-primary-light)",
                    color: "var(--theme-primary)",
                  }}
                >
                  {suggestion.icon}
                </span>
                <span
                  className="text-[13.5px] leading-[1.45] truncate"
                  style={{ color: "var(--theme-text-secondary)" }}
                >
                  {suggestion.text}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
});
