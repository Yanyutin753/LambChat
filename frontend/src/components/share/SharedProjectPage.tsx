/**
 * SharedProjectPage - Public view of a shared project (scope=project)
 *
 * Lists sessions in the project (full=live members / partial=snapshot).
 * Click a session to expand and view its messages, reusing ChatMessage.
 */

import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  ChevronDown,
  ChevronRight,
  Folder,
  Loader2,
  MessageSquare,
  Moon,
  Sun,
} from "lucide-react";

import { shareApi } from "../../services/api/share";
import type {
  SharedContentResponse,
  SharedProjectContentResponse,
  SharedProjectSessionItem,
} from "../../types";
import { APP_NAME, GITHUB_URL } from "../../constants";
import { BrandWordmark } from "../common/BrandWordmark";
import { formatDate } from "../../utils/datetime";
import { reconstructMessagesFromEvents } from "../../hooks/useAgent/historyLoader";

const ChatMessage = lazy(() =>
  import("../chat/ChatMessage").then((m) => ({ default: m.ChatMessage })),
);

// Theme management for shared pages (independent of main app context)
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

  // Enable page-level scrolling (global CSS sets overflow:hidden on html/body/#root),
  // so expanded sessions can scroll the page.
  useEffect(() => {
    document.documentElement.classList.add("allow-scroll");
    return () => document.documentElement.classList.remove("allow-scroll");
  }, []);

  const toggleTheme = () => {
    setTheme((prev) => (prev === "light" ? "dark" : "light"));
  };

  return { theme, toggleTheme };
}

function isEmojiIcon(icon?: string): boolean {
  if (!icon) return false;
  // 简单判定：单字符或典型 emoji 区间；lucide 图标名通常为英文
  return /\p{Extended_Pictographic}/u.test(icon) || [...icon].length <= 2;
}

export function SharedProjectPage({
  initialManifest,
}: {
  initialManifest?: SharedProjectContentResponse;
} = {}) {
  const { shareId } = useParams<{ shareId: string }>();
  const { t } = useTranslation();
  const { theme, toggleTheme } = useSharedPageTheme();

  const [manifest, setManifest] = useState<SharedProjectContentResponse | null>(
    initialManifest ?? null,
  );
  const [isLoading, setIsLoading] = useState(!initialManifest);
  const [error, setError] = useState<string | null>(null);

  // 展开的子会话：sessionId -> 内容
  const [expanded, setExpanded] = useState<Record<string, SharedContentResponse>>(
    {},
  );

  useEffect(() => {
    if (initialManifest) {
      setManifest(initialManifest);
      setIsLoading(false);
      return;
    }
    let cancelled = false;
    const load = async () => {
      if (!shareId) return;
      setIsLoading(true);
      setError(null);
      try {
        const data = await shareApi.getSharedContent(shareId);
        if (cancelled) return;
        if (!("sessions" in data)) {
          setError("not_project");
          return;
        }
        setManifest(data);
      } catch {
        if (!cancelled) setError("load_failed");
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [shareId, initialManifest]);

  const toggleSession = useCallback(
    async (session: SharedProjectSessionItem) => {
      if (!shareId) return;
      // 已展开则收起
      if (expanded[session.id]) {
        setExpanded((prev) => {
          const next = { ...prev };
          delete next[session.id];
          return next;
        });
        return;
      }
      // 展开并加载该子会话事件（展开态期间 content 为空，自动显示加载占位）
      try {
        const content = await shareApi.getSessionContentInProject(
          shareId,
          session.id,
        );
        setExpanded((prev) => ({ ...prev, [session.id]: content }));
      } catch {
        // 单个子会话加载失败不阻断整体
      }
    },
    [shareId, expanded],
  );

  const owner = manifest?.owner;

  if (isLoading) {
    return (
      <div className="min-h-dvh bg-theme-bg text-theme-text flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-theme-text-secondary" />
      </div>
    );
  }

  if (error || !manifest) {
    return (
      <div className="min-h-dvh bg-theme-bg text-theme-text flex items-center justify-center p-4">
        <div className="bg-theme-bg-card rounded-2xl shadow-xl border border-theme-border px-8 py-10 max-w-md text-center">
          <AlertCircle className="h-10 w-10 mx-auto mb-4 text-theme-text-secondary" />
          <h1 className="text-xl font-semibold mb-2">
            {error === "not_project"
              ? "这不是一个项目分享链接"
              : "分享不存在或已失效"}
          </h1>
          <p className="text-theme-text-secondary text-sm">
            {t("share.pageUnavailable", "链接可能已删除或无访问权限。")}
          </p>
        </div>
      </div>
    );
  }

  const projectIcon = manifest.project.icon;

  return (
    <div className="flex flex-col bg-theme-bg text-theme-text min-h-dvh font-sans">
      {/* Header */}
      <header className="safe-area-top sticky top-0 z-40 border-b border-theme-border bg-[color-mix(in_srgb,var(--theme-bg-card)_82%,transparent)] backdrop-blur">
        <div className="max-w-4xl lg:max-w-5xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between gap-3">
          <BrandWordmark
            decorative
            className="h-7 w-auto text-theme-text"
          />
          <button
            type="button"
            onClick={toggleTheme}
            className="p-2 rounded-lg text-theme-text-secondary hover:bg-theme-bg-subtle hover:text-theme-text transition-colors"
            aria-label="Toggle theme"
          >
            {theme === "light" ? (
              <Moon size={18} />
            ) : (
              <Sun size={18} />
            )}
          </button>
        </div>
      </header>

      {/* Project cover */}
      <section className="border-b border-theme-border">
        <div className="max-w-4xl lg:max-w-5xl mx-auto px-4 sm:px-6 py-8 sm:py-10">
          <div className="flex items-start gap-4">
            <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-theme-bg-subtle border border-theme-border text-2xl">
              {isEmojiIcon(projectIcon) ? (
                <span>{projectIcon || "📁"}</span>
              ) : (
                <Folder className="h-7 w-7 text-theme-text-secondary" />
              )}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs uppercase tracking-wider text-theme-text-secondary mb-1">
                {t("share.sharedProject", "分享的项目")}
              </p>
              <h1 className="text-2xl sm:text-3xl font-serif tracking-tight font-semibold break-words">
                {manifest.project.name}
              </h1>
              <div className="mt-2 flex items-center gap-2 text-sm text-theme-text-secondary">
                <MessageSquare size={14} />
                <span>
                  {manifest.sessions_total} {t("share.conversations", "个会话")}
                </span>
                {owner ? (
                  <>
                    <span className="opacity-50">·</span>
                    <span>{owner.username}</span>
                  </>
                ) : null}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Session list */}
      <main className="flex-1">
        <div className="max-w-4xl lg:max-w-5xl mx-auto px-4 sm:px-6 py-6">
          <ul className="space-y-2">
            {manifest.sessions.map((session) => {
              const isExpanded = !!expanded[session.id];
              const content = expanded[session.id];
              return (
                <li
                  key={session.id}
                  className="rounded-xl border border-theme-border bg-theme-bg-card overflow-hidden"
                >
                  <button
                    type="button"
                    onClick={() => toggleSession(session)}
                    className="w-full flex items-center gap-3 px-4 py-3.5 text-left hover:bg-theme-bg-subtle transition-colors"
                  >
                    <span className="text-theme-text-secondary shrink-0">
                      {isExpanded ? (
                        <ChevronDown size={18} />
                      ) : (
                        <ChevronRight size={18} />
                      )}
                    </span>
                    <span className="flex-1 min-w-0">
                      <span className="block font-medium truncate">
                        {session.name || t("share.untitledSession", "未命名会话")}
                      </span>
                      <span className="block text-xs text-theme-text-secondary truncate">
                        {session.agent_name}
                        {session.updated_at
                          ? ` · ${formatDate(session.updated_at)}`
                          : ""}
                      </span>
                    </span>
                  </button>

                  {isExpanded && (
                    <div className="border-t border-theme-border bg-theme-bg px-4 sm:px-6 py-4">
                      {content ? (
                        <SessionMessages content={content} />
                      ) : (
                        <div className="flex items-center justify-center py-8">
                          <Loader2 className="h-6 w-6 animate-spin text-theme-text-secondary" />
                        </div>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>

          {manifest.sessions.length === 0 ? (
            <div className="text-center py-16 text-theme-text-secondary">
              {t("share.emptyProject", "项目中暂无可分享的会话")}
            </div>
          ) : null}
        </div>
      </main>

      {/* Footer */}
      <footer className="safe-area-bottom border-t border-theme-border">
        <div className="max-w-4xl lg:max-w-5xl mx-auto px-4 sm:px-6 py-6 flex items-center justify-between text-sm text-theme-text-secondary">
          <span>{APP_NAME}</span>
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-theme-text transition-colors"
          >
            GitHub
          </a>
        </div>
      </footer>
    </div>
  );
}

function SessionMessages({ content }: { content: SharedContentResponse }) {
  const messages = useMemo(() => {
    if (!content?.events) return [];
    return reconstructMessagesFromEvents(content.events, new Set(), {
      activeSubagentStack: [],
    });
  }, [content?.events]);

  if (messages.length === 0) {
    return (
      <p className="text-center text-theme-text-secondary py-6 text-sm">
        暂无消息
      </p>
    );
  }

  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-theme-text-secondary" />
        </div>
      }
    >
      <div className="space-y-2">
        {messages.map((message, index) => (
          <div key={message.id} className="animate-in fade-in">
            <ChatMessage
              message={message}
              sessionId={content.session.id}
              isLastMessage={index === messages.length - 1}
              showFeedbackAndShareActions={false}
              isFirst={index === 0}
            />
          </div>
        ))}
      </div>
    </Suspense>
  );
}
