/**
 * SharedPage - Public view of a shared session
 * ChatGPT-inspired design with theme support and mobile responsiveness
 */

import { useEffect, useState, useMemo, useRef, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  ArrowLeft,
  MessageSquare,
  Sun,
  Moon,
  ExternalLink,
  Lock,
  Languages,
  MessageCircle,
  Check,
  Loader2,
  XCircle,
} from "lucide-react";
import { Loading } from "../common/LoadingSpinner";
import { shareApi } from "../../services/api/share";
import type { SharedContentResponse } from "../../types";
import { ChatMessage } from "../chat/ChatMessage";
import { RevealPreviewHost } from "../chat/ChatMessage/items/RevealPreviewHost";
import { PersistentToolPanelHost } from "../chat/ChatMessage/items/persistentToolPanelState";
import type { RevealPreviewRequest } from "../chat/ChatMessage/items/revealPreviewData";
import { getLatestAutoPreviewTarget } from "../chat/ChatMessage/autoPreviewEligibility";
import {
  createActiveRevealPreviewState,
  markRevealPreviewInteracted,
  shouldAcceptRevealPreviewOpen,
  type ActiveRevealPreviewState,
  type RevealPreviewOpenSource,
} from "../chat/ChatMessage/items/revealPreviewState";
import { reconstructMessagesFromEvents } from "../../hooks/useAgent/historyLoader";
import { APP_NAME, GITHUB_URL } from "../../constants";
import { getModelIconUrl, isMonochromeIcon } from "../agent/modelIcon";
import { ScrollButtons } from "../landing/components/ScrollButtons";

const LANGUAGES = [
  { code: "en", nativeName: "English" },
  { code: "zh", nativeName: "中文" },
  { code: "ja", nativeName: "日本語" },
  { code: "ko", nativeName: "한국어" },
  { code: "ru", nativeName: "Русский" },
];

/** Local-only language toggle — no backend API calls (safe for unauthenticated shared pages) */
function SharedPageLanguageToggle() {
  const { i18n, t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const selectLanguage = useCallback(
    (code: string) => {
      i18n.changeLanguage(code);
      localStorage.setItem("language", code);
      setIsOpen(false);
    },
    [i18n],
  );

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center justify-center w-9 h-9 rounded-xl bg-stone-100 dark:bg-stone-800 hover:bg-stone-200 dark:hover:bg-stone-700 transition-all duration-200 hover:scale-105 active:scale-95"
        title={t("common.language")}
        aria-label={t("common.language")}
      >
        <Languages size={18} className="text-stone-600 dark:text-stone-300" />
      </button>
      {isOpen && (
        <div className="absolute right-0 mt-2 w-40 rounded-lg bg-white dark:bg-stone-800 shadow-lg border border-stone-200 dark:border-stone-700 py-1 z-50">
          {LANGUAGES.map((lang) => (
            <button
              key={lang.code}
              onClick={() => selectLanguage(lang.code)}
              className={`w-full px-4 py-2 text-left text-sm flex items-center justify-between transition-colors ${
                i18n.language === lang.code
                  ? "bg-stone-100 dark:bg-stone-700 text-stone-900 dark:text-stone-100"
                  : "text-stone-700 dark:text-stone-200 hover:bg-stone-50 dark:hover:bg-stone-700/50"
              }`}
            >
              <span>{lang.nativeName}</span>
              {i18n.language === lang.code && (
                <Check
                  size={16}
                  className="text-stone-700 dark:text-stone-200"
                />
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

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
  const [imgError, setImgError] = useState(false);
  const [showScrollTop, setShowScrollTop] = useState(false);
  const [showScrollBottom, setShowScrollBottom] = useState(true);
  const [scrollProgress, setScrollProgress] = useState(0);

  const handleScroll = useCallback(() => {
    const win = window;
    const threshold = 200;
    const scrollY = win.scrollY;
    const docHeight =
      win.document.documentElement.scrollHeight - win.innerHeight;
    setShowScrollTop(scrollY > threshold);
    setShowScrollBottom(scrollY < docHeight - threshold);
    setScrollProgress(docHeight > 0 ? Math.min(scrollY / docHeight, 1) : 0);
  }, []);

  useEffect(() => {
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, [handleScroll]);

  const scrollToTop = useCallback(() => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  const scrollToBottom = useCallback(() => {
    window.scrollTo({
      top: document.documentElement.scrollHeight,
      behavior: "smooth",
    });
  }, []);

  // Enable page-level scrolling (global CSS sets overflow:hidden on html/body/#root)
  useEffect(() => {
    document.documentElement.classList.add("allow-scroll");
    return () => document.documentElement.classList.remove("allow-scroll");
  }, []);

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

  const [activePreviewState, setActivePreviewState] =
    useState<ActiveRevealPreviewState | null>(null);
  const activePreviewStateRef = useRef<ActiveRevealPreviewState | null>(null);
  const dismissedPreviewKeysRef = useRef<Set<string>>(new Set());
  const activePreview = activePreviewState?.request ?? null;

  useEffect(() => {
    activePreviewStateRef.current = activePreviewState;
  }, [activePreviewState]);

  const handleOpenPreview = useCallback(
    (
      preview: RevealPreviewRequest,
      source: RevealPreviewOpenSource = "manual",
    ) => {
      const shouldOpen = shouldAcceptRevealPreviewOpen({
        activePreview: activePreviewStateRef.current,
        nextPreview: preview,
        source,
        dismissedPreviewKeys: dismissedPreviewKeysRef.current,
      });

      if (!shouldOpen) {
        return false;
      }

      if (source === "manual") {
        dismissedPreviewKeysRef.current.delete(preview.previewKey);
      }

      setActivePreviewState(createActiveRevealPreviewState(preview, source));
      return true;
    },
    [],
  );

  const handleClosePreview = useCallback((dismiss = true) => {
    const currentPreview = activePreviewStateRef.current;
    if (dismiss && currentPreview) {
      dismissedPreviewKeysRef.current.add(currentPreview.request.previewKey);
    }
    setActivePreviewState(null);
  }, []);

  const handlePreviewInteraction = useCallback(() => {
    setActivePreviewState((current) => markRevealPreviewInteracted(current));
  }, []);

  const latestAutoPreview = useMemo(
    () => getLatestAutoPreviewTarget(messages),
    [messages],
  );

  // Reading time estimate (rough: ~200 words per minute)
  const readingTime = useMemo(() => {
    const totalWords = messages.reduce((acc, m) => {
      if (typeof m.content === "string") {
        return acc + m.content.split(/\s+/).length;
      }
      return acc;
    }, 0);
    const minutes = Math.ceil(totalWords / 200);
    return minutes < 1
      ? t("share.lessThanOneMin")
      : t("share.readingTime", { count: minutes });
  }, [messages, t]);

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

  // Update document title and SEO meta tags for shared pages
  useEffect(() => {
    if (!data) return;

    const title = data.session.name
      ? `${data.session.name} - ${APP_NAME}`
      : `${APP_NAME} - ${t("share.sharedConversation")}`;

    document.title = title;

    const setDescription = (content: string) => {
      let el = document.querySelector('meta[name="description"]');
      if (!el) {
        el = document.createElement("meta");
        el.setAttribute("name", "description");
        document.head.appendChild(el);
      }
      el.setAttribute("content", content);
    };

    const setOg = (property: string, content: string) => {
      let el = document.querySelector(`meta[property="${property}"]`);
      if (!el) {
        el = document.createElement("meta");
        el.setAttribute("property", property);
        document.head.appendChild(el);
      }
      el.setAttribute("content", content);
    };

    const setTwitter = (name: string, content: string) => {
      let el = document.querySelector(`meta[name="${name}"]`);
      if (!el) {
        el = document.createElement("meta");
        el.setAttribute("name", name);
        document.head.appendChild(el);
      }
      el.setAttribute("content", content);
    };

    const setCanonical = (href: string) => {
      let el = document.querySelector('link[rel="canonical"]');
      if (!el) {
        el = document.createElement("link");
        el.setAttribute("rel", "canonical");
        document.head.appendChild(el);
      }
      el.setAttribute("href", href);
    };

    // Build a description from session metadata and conversation content
    const truncate = (s: string, max: number) =>
      s.length > max ? s.substring(0, max).replace(/\s+\S*$/, "") + "…" : s;

    const descLines: string[] = [];
    const firstUser = messages.find((m) => m.role === "user");
    const firstAssistant = messages.find((m) => m.role === "assistant");

    if (firstUser?.content && typeof firstUser.content === "string") {
      descLines.push(truncate(firstUser.content, 120));
    }
    if (firstAssistant?.content && typeof firstAssistant.content === "string") {
      descLines.push(truncate(firstAssistant.content, 120));
    }

    const metaParts: string[] = [];
    if (data.session.agent_name) metaParts.push(data.session.agent_name);
    if (data.session.model) metaParts.push(data.session.model);
    if (messages.length > 0) metaParts.push(`${messages.length} messages`);

    const conversationPreview =
      descLines.length > 0 ? descLines.join(" → ") : "";
    const metaSuffix = metaParts.length > 0 ? metaParts.join(" · ") : "";

    const description = [conversationPreview, metaSuffix]
      .filter(Boolean)
      .join("\n");

    setDescription(description);
    setCanonical(window.location.href);

    // Open Graph
    setOg("og:title", title);
    setOg("og:description", description);
    setOg("og:url", window.location.href);
    setOg("og:type", "article");

    // Twitter Card
    setTwitter("twitter:title", title);
    setTwitter("twitter:description", description);

    return () => {
      document.title = `${APP_NAME} - AI Agent Platform`;
      setDescription(
        "LambChat is a pluggable, multi-tenant AI conversation platform. Skills + MCP dual-engine driven, supporting Claude, GPT, Gemini and more.",
      );
    };
  }, [data, messages, t]);

  // Loading state
  if (isLoading) {
    return (
      <div className="min-h-dvh bg-[#faf9f7] dark:bg-[#0f0e0d] flex items-center justify-center">
        <div className="flex flex-col items-center gap-6 animate-in fade-in duration-500">
          <Loading text={t("common.loading")} />
        </div>
      </div>
    );
  }

  // Auth required error
  if (error === "auth_required") {
    return (
      <div className="min-h-dvh bg-[#faf9f7] dark:bg-[#0f0e0d] flex items-center justify-center p-4">
        <div className="max-w-md w-full animate-in fade-in slide-in-from-bottom-4 duration-500">
          <div className="bg-white dark:bg-stone-900 rounded-2xl shadow-xl shadow-stone-900/5 dark:shadow-black/30 border border-stone-200/60 dark:border-stone-800/60 overflow-hidden">
            <div className="p-8 text-center">
              <div className="w-16 h-16 mx-auto mb-6 rounded-2xl bg-amber-50 dark:bg-amber-900/20 flex items-center justify-center">
                <Lock
                  size={28}
                  className="text-amber-500 dark:text-amber-400"
                />
              </div>
              <h1 className="text-xl font-semibold text-stone-900 dark:text-stone-100 font-serif mb-2 font-serif tracking-tight">
                {t("share.loginRequired")}
              </h1>
              <p className="text-stone-500 dark:text-stone-400 mb-8 leading-relaxed">
                {t("share.loginRequiredDesc")}
              </p>
              <Link
                to="/auth/login"
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
      <div className="min-h-dvh bg-[#faf9f7] dark:bg-[#0f0e0d] flex items-center justify-center p-4">
        <div className="max-w-md w-full animate-in fade-in slide-in-from-bottom-4 duration-500">
          <div className="bg-white dark:bg-stone-900 rounded-2xl shadow-xl shadow-stone-900/5 dark:shadow-black/30 border border-stone-200/60 dark:border-stone-800/60 overflow-hidden">
            <div className="p-8 text-center">
              <div className="w-16 h-16 mx-auto mb-6 rounded-2xl bg-red-50 dark:bg-red-900/20 flex items-center justify-center">
                <AlertCircle
                  size={28}
                  className="text-red-500 dark:text-red-400"
                />
              </div>
              <h1 className="text-xl font-semibold text-stone-900 dark:text-stone-100 font-serif mb-2 font-serif tracking-tight">
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

  // Main content — editorial blog layout
  return (
    <div className="flex flex-col bg-[#faf9f7] dark:bg-[#0f0e0d] min-h-dvh font-sans">
      {/* Top bar — matching landing page Navbar style */}
      <header
        data-yields-sidebar
        className="fixed top-0 inset-x-0 z-50 bg-white/80 dark:bg-stone-950/80 border-b border-stone-100/60 dark:border-stone-800/40"
      >
        {/* Scroll progress bar */}
        <div
          className="absolute bottom-0 left-0 h-[2px] landing-progress-bar"
          style={{ width: `${scrollProgress * 100}%` }}
        />
        <div className="max-w-6xl mx-auto px-4 sm:px-8 h-14 flex items-center justify-between">
          {/* Left: Brand */}
          <Link
            to="/"
            className="flex items-center gap-2.5 cursor-pointer group"
          >
            <img
              src="/icons/icon.svg"
              alt=""
              className="w-6 h-6 sm:w-7 sm:h-7 rounded-lg transition-transform duration-300 group-hover:scale-105"
            />
            <span className="text-md sm:text-lg font-bold tracking-tight text-stone-900 dark:text-stone-100 font-serif">
              {APP_NAME}
            </span>
          </Link>

          {/* Right: Controls */}
          <div className="flex items-center gap-1.5 flex-shrink-0">
            <Link
              to="/"
              className="flex items-center justify-center w-9 h-9 rounded-xl bg-stone-100 dark:bg-stone-800 hover:bg-stone-200 dark:hover:bg-stone-700 text-stone-600 dark:text-stone-300 transition-all duration-200 hover:scale-105 active:scale-95"
              title={t("share.goToChat")}
              aria-label={t("share.goToChat")}
            >
              <MessageCircle size={18} />
            </Link>
            <SharedPageLanguageToggle />
            <button
              onClick={toggleTheme}
              className="flex items-center justify-center w-9 h-9 rounded-xl bg-stone-100 dark:bg-stone-800 hover:bg-stone-200 dark:hover:bg-stone-700 transition-all duration-200 hover:scale-105 active:scale-95"
              title={
                theme === "light"
                  ? t("theme.switchToDark")
                  : t("theme.switchToLight")
              }
            >
              {theme === "light" ? (
                <Moon
                  size={18}
                  className="text-stone-600 dark:text-stone-300"
                />
              ) : (
                <Sun size={18} className="text-amber-400" />
              )}
            </button>
          </div>
        </div>
      </header>

      {/* Scrollable article area */}
      <main className="relative flex-1 overflow-x-hidden scroll-smooth">
        <article className="max-w-3xl sm:max-w-5xl mx-auto">
          {/* Editorial hero */}
          <header className="pt-20 sm:pt-28 lg:pt-36 pb-0 animate-in fade-in duration-800">
            {/* Overline label */}
            <div className="text-center mb-5">
              <span className="inline-block text-[11px] font-semibold tracking-[0.15em] uppercase text-stone-400 dark:text-stone-500">
                {t("share.sharedConversation")}
              </span>
            </div>

            {/* Title */}
            <h1 className="text-[1.75rem] sm:text-4xl lg:text-[2.75rem] font-light text-stone-900 dark:text-[#e8e6e1] text-center leading-[1.2] tracking-[-0.01em] max-w-3xl mx-auto font-serif">
              {sessionTitle}
            </h1>

            {/* Author + meta strip */}
            <div className="mt-10 sm:mt-14 flex flex-col items-center gap-4 sm:gap-5">
              {/* Author */}
              <div className="flex items-center gap-3">
                {data.owner.avatar_url && !imgError ? (
                  <img
                    src={data.owner.avatar_url}
                    alt={data.owner.username}
                    className="size-10 rounded-full object-cover grayscale-[20%] dark:grayscale-[10%] flex-shrink-0 ring-2 ring-stone-100 dark:ring-stone-800"
                    onError={() => setImgError(true)}
                  />
                ) : (
                  <img
                    src="/icons/icon.svg"
                    alt=""
                    className="size-10 rounded-full flex-shrink-0 ring-2 ring-stone-100 dark:ring-stone-800"
                  />
                )}
                <div className="space-y-1">
                  <div className="text-[13px] font-semibold text-stone-800 dark:text-stone-200">
                    {data.owner.username}
                  </div>
                  {data.session.created_at && (
                    <div className="text-[11px] text-stone-400 dark:text-stone-500 mt-0.5 tracking-wide">
                      {new Date(data.session.created_at).toLocaleDateString(
                        undefined,
                        {
                          month: "long",
                          day: "numeric",
                          year: "numeric",
                        },
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* Meta chips row */}
              <div className="flex flex-wrap items-center justify-center gap-2 sm:gap-3 px-6">
                {messages.length > 0 && (
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-stone-100/80 dark:bg-stone-800/60 text-[11px] text-stone-500 dark:text-stone-400 font-medium">
                    <MessageSquare size={11} />
                    {messages.length} {t("share.messages")}
                  </span>
                )}
                {data.session.agent_name && (
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-stone-100/80 dark:bg-stone-800/60 text-[11px] text-stone-500 dark:text-stone-400 font-medium">
                    {data.session.agent_name}
                  </span>
                )}
                {data.session.model && (
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-stone-100/80 dark:bg-stone-800/60 text-[11px] text-stone-500 dark:text-stone-400 font-medium">
                    {(() => {
                      const iconUrl = getModelIconUrl(
                        data.session.model,
                        (data.session as Record<string, unknown>).provider as
                          | string
                          | undefined,
                      );
                      const mono = isMonochromeIcon(
                        data.session.model,
                        (data.session as Record<string, unknown>).provider as
                          | string
                          | undefined,
                      );
                      return iconUrl ? (
                        <img
                          src={iconUrl}
                          alt=""
                          className={`w-3.5 h-3.5 ${mono ? "dark:invert" : ""}`}
                        />
                      ) : null;
                    })()}
                    {data.session.model}
                  </span>
                )}
                <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-stone-100/80 dark:bg-stone-800/60 text-[11px] text-stone-500 dark:text-stone-400 font-medium">
                  {readingTime}
                </span>
              </div>
            </div>

            {/* Status badge */}
            {data.session.task_status &&
              data.session.task_status !== "completed" && (
                <div className="mt-5 flex justify-center">
                  <span
                    className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-medium ${
                      data.session.task_status === "failed"
                        ? "bg-red-50 dark:bg-red-950/30 text-red-500"
                        : data.session.task_status === "running"
                          ? "bg-sky-50 dark:bg-sky-950/30 text-sky-500"
                          : "bg-stone-100 dark:bg-stone-800 text-stone-500"
                    }`}
                  >
                    {data.session.task_status === "running" && (
                      <Loader2 size={10} className="animate-spin" />
                    )}
                    {data.session.task_status === "failed" && (
                      <XCircle size={10} />
                    )}
                    {data.session.task_status === "running" &&
                      t("share.taskRunning")}
                    {data.session.task_status === "failed" &&
                      t("share.taskFailed")}
                    {data.session.task_status === "pending" &&
                      t("share.taskPending")}
                  </span>
                </div>
              )}
          </header>

          {/* Messages */}
          {messages.length === 0 ? (
            <div className="text-center py-24 sm:py-32">
              <div className="w-14 h-14 mx-auto mb-5 rounded-2xl bg-stone-100 dark:bg-stone-800/60 flex items-center justify-center">
                <MessageSquare
                  size={22}
                  className="text-stone-300 dark:text-stone-600"
                />
              </div>
              <p className="text-stone-400 dark:text-stone-500 text-sm font-serif">
                {t("share.noMessages")}
              </p>
            </div>
          ) : (
            <div className="py-8 sm:py-12">
              {/* Opening divider */}
              <div className="flex items-center gap-3 mb-8 sm:mb-12">
                <div className="flex-1 h-px bg-gradient-to-r from-transparent via-stone-200/80 dark:via-stone-700/50 to-transparent" />
                <span className="flex-shrink-0 text-[10px] font-semibold tracking-[0.18em] uppercase text-stone-400 dark:text-stone-500 font-mono tabular-nums select-none">
                  {t("share.conversationHistory")}
                </span>
                <div className="flex-1 h-px bg-gradient-to-r from-transparent via-stone-200/80 dark:via-stone-700/50 to-transparent" />
              </div>

              {messages.map((message, index) => (
                <div
                  key={message.id}
                  className="animate-in fade-in"
                  style={{ animationDelay: `${Math.min(index * 30, 200)}ms` }}
                >
                  <ChatMessage
                    message={message}
                    sessionId={data.session.id}
                    sessionName={data.session.name}
                    runId={data.run_ids?.[0]}
                    isLastMessage={index === messages.length - 1}
                    activePreview={activePreview}
                    latestAutoPreview={latestAutoPreview}
                    onOpenPreview={handleOpenPreview}
                  />
                </div>
              ))}
            </div>
          )}
        </article>
      </main>

      {/* Footer */}
      <footer className="relative mt-auto">
        <div className="max-w-3xl sm:max-w-5xl mx-auto px-5 sm:px-6">
          {/* CTA card */}
          <div className="relative mx-4 sm:mx-0 mb-10 sm:mb-14 rounded-2xl sm:rounded-3xl border border-stone-200/70 dark:border-stone-800/50 bg-gradient-to-br from-white/80 to-stone-50/60 dark:from-stone-900/60 dark:to-stone-950/40 overflow-hidden">
            {/* Inner accent */}
            <div className="absolute top-0 left-1/2 -translate-x-1/2 w-24 sm:w-32 h-px bg-gradient-to-r from-transparent via-amber-400/30 dark:via-amber-500/15 to-transparent" />

            <div className="py-8 sm:py-10 px-6 sm:px-8 flex flex-col sm:flex-row items-center gap-5 sm:gap-6">
              {/* Left text */}
              <div className="flex-1 text-center sm:text-left">
                <p className="text-[14px] sm:text-[15px] font-semibold text-stone-800 dark:text-stone-200 tracking-tight font-serif">
                  {t("share.createYourOwn")}
                </p>
                <p className="mt-1 text-[12px] text-stone-400 dark:text-stone-500 font-serif">
                  {APP_NAME} &middot; Open Source &middot; MIT
                </p>
              </div>

              {/* Button */}
              <Link
                to="/"
                className="group flex-shrink-0 inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-[13px] font-semibold text-white bg-stone-900 dark:bg-stone-100 dark:text-stone-900 hover:bg-stone-800 dark:hover:bg-stone-200 active:scale-[0.97] transition-all duration-200 shadow-sm hover:shadow-md font-serif"
              >
                <img src="/icons/icon.svg" alt="" className="w-4 h-4 rounded" />
                {APP_NAME}
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="transition-transform duration-200 group-hover:translate-x-0.5"
                >
                  <path d="M5 12h14" />
                  <path d="m12 5 7 7-7 7" />
                </svg>
              </Link>
            </div>
          </div>

          {/* Bottom meta bar */}
          <div className="pb-6 sm:pb-8 flex flex-col sm:flex-row items-center justify-between gap-2.5">
            <div className="flex items-center gap-2 text-[11px] text-stone-300 dark:text-stone-600">
              {data.session.created_at && (
                <>
                  <span>
                    {new Date(data.session.created_at).toLocaleDateString(
                      undefined,
                      { year: "numeric", month: "short", day: "numeric" },
                    )}
                  </span>
                  <span className="w-0.5 h-0.5 rounded-full bg-stone-200 dark:bg-stone-700" />
                </>
              )}
              <span>
                {messages.length} {t("share.messages")}
              </span>
              <span className="w-0.5 h-0.5 rounded-full bg-stone-200 dark:bg-stone-700" />
              <span>{readingTime}</span>
            </div>

            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="text-stone-300 dark:text-stone-700 hover:text-stone-500 dark:hover:text-stone-400 transition-colors duration-200"
              aria-label="GitHub"
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="currentColor"
              >
                <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0112 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z" />
              </svg>
            </a>
          </div>
        </div>
      </footer>

      {/* Scroll buttons */}
      <ScrollButtons
        showTop={showScrollTop}
        showBottom={showScrollBottom}
        onScrollToTop={scrollToTop}
        onScrollToBottom={scrollToBottom}
      />

      <RevealPreviewHost
        preview={activePreview}
        onClose={() => handleClosePreview(true)}
        onUserInteraction={handlePreviewInteraction}
      />
      <PersistentToolPanelHost />
    </div>
  );
}
