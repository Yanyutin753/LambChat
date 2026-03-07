/**
 * SharedPage - Public view of a shared session
 * ChatGPT-inspired design with theme support and mobile responsiveness
 */

import { useEffect, useState, useMemo } from "react";
import { useParams, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  ArrowLeft,
  MessageSquare,
  User,
  Calendar,
  Sun,
  Moon,
  ExternalLink,
  Eye,
  Lock,
} from "lucide-react";
import { LanguageToggle } from "../common/LanguageToggle";
import { Loading } from "../common/LoadingSpinner";
import { shareApi } from "../../services/api/share";
import type { SharedContentResponse } from "../../types";
import { ChatMessage } from "../chat/ChatMessage";
import { reconstructMessagesFromEvents } from "../../hooks/useAgent/historyLoader";

// Theme management for shared page (independent of main app context)
function useSharedPageTheme() {
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem("lamb-agent-theme");
      if (stored === "light" || stored === "dark") {
        return stored;
      }
      if (window.matchMedia("(prefers-color-scheme: dark)").matches) {
        return "dark";
      }
    }
    return "light";
  });

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "dark") {
      root.classList.add("dark");
    } else {
      root.classList.remove("dark");
    }
    localStorage.setItem("lamb-agent-theme", theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === "light" ? "dark" : "light"));
  };

  return { theme, toggleTheme };
}

export function SharedPage() {
  const { shareId } = useParams<{ shareId: string }>();
  const { t } = useTranslation();
  const { theme, toggleTheme } = useSharedPageTheme();

  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<SharedContentResponse | null>(null);

  useEffect(() => {
    if (!shareId) {
      setError("Invalid share link");
      setIsLoading(false);
      return;
    }

    const loadSharedContent = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const response = await shareApi.getSharedContent(shareId);
        setData(response);
      } catch (err) {
        console.error("Failed to load shared content:", err);
        if (err instanceof Error) {
          if (err.message.includes("401") || err.message.includes("需要登录")) {
            setError("auth_required");
          } else if (
            err.message.includes("404") ||
            err.message.includes("不存在")
          ) {
            setError("not_found");
          } else {
            setError(err.message);
          }
        } else {
          setError("Failed to load shared content");
        }
      } finally {
        setIsLoading(false);
      }
    };

    loadSharedContent();
  }, [shareId]);

  // Reconstruct messages from events using the same logic as the main chat
  const messages = useMemo(() => {
    if (!data?.events) return [];
    return reconstructMessagesFromEvents(data.events, new Set(), {
      activeSubagentStack: [],
    });
  }, [data?.events]);

  // Derive session title from session name or first user message
  const sessionTitle = useMemo(() => {
    if (data?.session?.name) return data.session.name;
    // Fallback to first user message as title
    const firstUserMessage = messages.find((m) => m.role === "user");
    if (firstUserMessage?.content) {
      // Truncate long messages for title
      const content = firstUserMessage.content;
      return content.length > 50 ? content.substring(0, 50) + "..." : content;
    }
    return t("sidebar.newChat");
  }, [data?.session?.name, messages, t]);

  // Loading state
  if (isLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-stone-50 to-white dark:from-stone-950 dark:to-stone-900 flex items-center justify-center">
        <div className="flex flex-col items-center gap-6 animate-in fade-in duration-500">
          {/* Animated logo */}
          <div className="relative">
            <div className="size-12 rounded-2xl bg-white dark:bg-stone-800 flex items-center justify-center shadow-xl shadow-stone-900/10 dark:shadow-stone-950/50 border border-stone-200 dark:border-stone-700">
              <img
                src="/icons/icon.svg"
                alt="LambChat"
                className="size-8 rounded-full"
              />
            </div>
            <div className="absolute -inset-1 rounded-2xl bg-gradient-to-br from-stone-400/20 to-stone-600/20 blur-xl animate-pulse" />
          </div>
          <Loading text={t("common.loading")} />
        </div>
      </div>
    );
  }

  // Auth required error
  if (error === "auth_required") {
    return (
      <div className="min-h-screen bg-gradient-to-b from-stone-50 to-white dark:from-stone-950 dark:to-stone-900 flex items-center justify-center p-4">
        <div className="max-w-md w-full animate-in fade-in slide-in-from-bottom-4 duration-500">
          <div className="bg-white dark:bg-stone-900 rounded-2xl shadow-2xl shadow-stone-900/5 dark:shadow-black/40 border border-stone-200/50 dark:border-stone-800/50 overflow-hidden">
            <div className="p-8 text-center">
              <div className="w-16 h-16 mx-auto mb-6 rounded-2xl bg-amber-50 dark:bg-amber-900/20 flex items-center justify-center">
                <Lock
                  size={28}
                  className="text-amber-500 dark:text-amber-400"
                />
              </div>
              <h1 className="text-xl font-semibold text-stone-900 dark:text-stone-100 mb-2 font-serif tracking-tight">
                {t("share.loginRequired")}
              </h1>
              <p className="text-stone-500 dark:text-stone-400 mb-8 leading-relaxed">
                {t("share.loginRequiredDesc")}
              </p>
              <Link
                to="/login"
                className="inline-flex items-center gap-2 px-6 py-3 bg-stone-900 dark:bg-stone-100 hover:bg-stone-800 dark:hover:bg-stone-200 text-white dark:text-stone-900 rounded-xl font-medium transition-all duration-200 hover:scale-[1.02] active:scale-[0.98]"
              >
                {t("auth.loginNow")}
                <ExternalLink size={16} />
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Not found error
  if (error === "not_found" || !data) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-stone-50 to-white dark:from-stone-950 dark:to-stone-900 flex items-center justify-center p-4">
        <div className="max-w-md w-full animate-in fade-in slide-in-from-bottom-4 duration-500">
          <div className="bg-white dark:bg-stone-900 rounded-2xl shadow-2xl shadow-stone-900/5 dark:shadow-black/40 border border-stone-200/50 dark:border-stone-800/50 overflow-hidden">
            <div className="p-8 text-center">
              <div className="w-16 h-16 mx-auto mb-6 rounded-2xl bg-red-50 dark:bg-red-900/20 flex items-center justify-center">
                <AlertCircle
                  size={28}
                  className="text-red-500 dark:text-red-400"
                />
              </div>
              <h1 className="text-xl font-semibold text-stone-900 dark:text-stone-100 mb-2 font-serif tracking-tight">
                {t("share.notFound")}
              </h1>
              <p className="text-stone-500 dark:text-stone-400 mb-8 leading-relaxed">
                {t("share.notFoundDesc")}
              </p>
              <Link
                to="/"
                className="inline-flex items-center gap-2 px-6 py-3 bg-stone-900 dark:bg-stone-100 hover:bg-stone-800 dark:hover:bg-stone-200 text-white dark:text-stone-900 rounded-xl font-medium transition-all duration-200 hover:scale-[1.02] active:scale-[0.98]"
              >
                {t("errors.backToHome")}
                <ArrowLeft size={16} />
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Main content
  return (
    <div className="h-screen flex flex-col bg-gradient-to-b from-stone-50 to-white dark:from-stone-950 dark:to-stone-900">
      {/* Floating header with glass effect */}
      <header className="sticky top-0 z-50 backdrop-blur-xl bg-white/70 dark:bg-stone-900/70 border-b border-stone-200/50 dark:border-stone-800/50">
        <div className="max-w-3xl sm:max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            {/* Left: Back button */}
            <Link
              to="/"
              className="group flex items-center gap-2 text-stone-500 hover:text-stone-900 dark:text-stone-400 dark:hover:text-stone-100 transition-colors"
            >
              <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-stone-100 dark:bg-stone-800 group-hover:bg-stone-200 dark:group-hover:bg-stone-700 transition-colors">
                <ArrowLeft
                  size={18}
                  className="text-stone-600 dark:text-stone-300"
                />
              </div>
              <span className="hidden sm:inline text-sm font-medium">
                {t("errors.backToHome")}
              </span>
            </Link>

            {/* Center: Session title */}
            <div className="flex-1 min-w-0 px-4">
              <h1 className="text-base font-semibold text-stone-900 dark:text-stone-100 truncate text-center font-serif tracking-tight">
                {sessionTitle}
              </h1>
            </div>

            {/* Right: Language toggle and Theme toggle */}
            <div className="flex items-center gap-3">
              <LanguageToggle />
              <button
                onClick={toggleTheme}
                className="flex items-center justify-center w-9 h-9 rounded-xl bg-stone-100 dark:bg-stone-800 hover:bg-stone-200 dark:hover:bg-stone-700 transition-all duration-200 hover:scale-105 active:scale-95"
                title={
                  theme === "light"
                    ? "Switch to dark mode"
                    : "Switch to light mode"
                }
              >
                {theme === "light" ? (
                  <Moon size={18} className="text-stone-600" />
                ) : (
                  <Sun size={18} className="text-amber-400" />
                )}
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Messages - scrollable area with session info */}
      <main
        className="relative flex-1 overflow-y-auto overflow-x-hidden min-h-0 overscroll-contain pb-24"
        style={{
          WebkitOverflowScrolling: "touch",
          paddingBottom: "calc(env(safe-area-inset-bottom) + 10rem)",
        }}
      >
        <div className="max-w-3xl sm:max-w-5xl mx-auto">
          {/* Session info card */}
          <div className="py-8 px-4 sm:px-6 mx-auto max-w-3xl xl:max-w-5xl">
            <div className="animate-in fade-in slide-in-from-bottom-2 duration-500">
              <div className="bg-white dark:bg-stone-900 rounded-2xl border border-stone-200/60 dark:border-stone-800/60 shadow-lg shadow-stone-900/5 dark:shadow-black/20 overflow-hidden">
                {/* User info section */}
                <div className="p-5 sm:p-6">
                  <div className="flex flex-col sm:flex-row sm:items-center gap-4">
                    {/* Avatar and username */}
                    <div className="flex items-center gap-3">
                      {data.owner.avatar_url ? (
                        <img
                          src={data.owner.avatar_url}
                          alt={data.owner.username}
                          className="w-12 h-12 rounded-xl object-cover ring-2 ring-stone-100 dark:ring-stone-800"
                        />
                      ) : (
                        <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-stone-500 to-stone-700 flex items-center justify-center shadow-lg shadow-stone-500/20">
                          <User size={22} className="text-white" />
                        </div>
                      )}
                      <div className="space-y-1">
                        <div className="font-semibold text-stone-900 dark:text-stone-100">
                          {data.owner.username}
                        </div>
                        <div className="text-xs text-stone-400 dark:text-stone-500">
                          {t("share.sharedConversation")}
                        </div>
                      </div>
                    </div>

                    {/* Metadata badges */}
                    <div className="flex flex-wrap items-center gap-2 sm:ml-auto">
                      {data.session.created_at && (
                        <div className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-stone-100 dark:bg-stone-800/80 text-xs font-medium text-stone-600 dark:text-stone-300">
                          <Calendar size={13} className="text-stone-400" />
                          {new Date(data.session.created_at).toLocaleDateString(
                            undefined,
                            {
                              year: "numeric",
                              month: "short",
                              day: "numeric",
                            },
                          )}
                        </div>
                      )}
                      <div className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-stone-100 dark:bg-stone-800/80 text-xs font-medium text-stone-600 dark:text-stone-300">
                        <MessageSquare size={13} className="text-stone-400" />
                        {messages.length} {t("share.messages")}
                      </div>
                      <div className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-stone-100 dark:bg-stone-800/80 text-xs font-medium text-stone-600 dark:text-stone-300">
                        <Eye size={13} className="text-stone-400" />
                        {data.share_type === "full"
                          ? t("share.fullSession")
                          : t("share.partialSession")}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Read-only notice */}
                <div className="px-5 sm:px-6 pb-5 sm:pb-6">
                  <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-stone-50 dark:bg-stone-800/50 border border-stone-200/60 dark:border-stone-700/50">
                    <Lock size={14} className="text-stone-400 flex-shrink-0" />
                    <span className="text-sm text-stone-600 dark:text-stone-400">
                      {t("share.readOnlyNotice")}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Messages list */}
          {messages.length === 0 ? (
            <div className="text-center py-16">
              <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-stone-100 dark:bg-stone-800 flex items-center justify-center">
                <MessageSquare size={24} className="text-stone-400" />
              </div>
              <p className="text-stone-500 dark:text-stone-400">
                {t("share.noMessages")}
              </p>
            </div>
          ) : (
            <div className="space-y-1">
              {messages.map((message, index) => (
                <div
                  key={message.id}
                  className="animate-in fade-in slide-in-from-bottom-2"
                  style={{ animationDelay: `${Math.min(index * 50, 300)}ms` }}
                >
                  <ChatMessage message={message} />
                </div>
              ))}
            </div>
          )}
        </div>
      </main>

      {/* Fixed footer */}
      <footer className="fixed bottom-0 left-0 right-0 z-40 backdrop-blur-xl bg-white/80 dark:bg-stone-900/80 border-t border-stone-200/50 dark:border-stone-800/50">
        <div className="max-w-3xl sm:max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            {/* Logo */}
            <div className="flex items-center gap-2">
              <img
                src="/icons/icon.svg"
                alt="LambChat"
                className="size-8 rounded-full"
              />
              <span className="text-base font-semibold text-stone-700 dark:text-stone-300 tracking-tight font-serif">
                LambChat
              </span>
            </div>

            {/* CTA */}
            <Link
              to="/"
              className="group inline-flex items-center gap-2 text-sm font-medium text-stone-500 dark:text-stone-400 hover:text-stone-900 dark:hover:text-stone-100 transition-colors"
            >
              <span className="hidden sm:inline">
                {t("share.createYourOwn")}
              </span>
              <span className="sm:hidden">{t("share.createChat")}</span>
              <ExternalLink
                size={14}
                className="group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform"
              />
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
