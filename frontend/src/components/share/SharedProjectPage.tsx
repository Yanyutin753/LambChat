/**
 * SharedProjectPage - Public view of a shared project (scope=project)
 *
 * Lists sessions in the project (full=live members / partial=snapshot).
 * Click a session to expand and view its messages, reusing ChatMessage.
 */

import {
  lazy,
  Suspense,
  useCallback,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ChevronDown,
  ChevronRight,
  Coffee,
  Folder,
  MessageSquare,
  Moon,
  Sun,
} from "lucide-react";
import { useSharedPageTheme } from "./useSharedPageTheme";
import { shareApi } from "../../services/api/share";
import type {
  SharedContentResponse,
  SharedProjectContentResponse,
} from "../../types";
import { APP_NAME, GITHUB_URL } from "../../constants";
import { BrandWordmark } from "../common/BrandWordmark";
import { IconButton } from "../common/ui/IconButton";
import { Button } from "../common/ui/Button";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { LanguageToggle } from "../common/LanguageToggle";
import { formatDate } from "../../utils/datetime";
import { reconstructMessagesFromEvents } from "../../hooks/useAgent/historyLoader";
import { computeProjectHasMore } from "./sharedProjectPageState";

const ChatMessage = lazy(() =>
  import("../chat/ChatMessage").then((m) => ({ default: m.ChatMessage })),
);

// 项目分享 manifest 单次分页大小（后端上限 SHARE_PROJECT_SESSIONS_LIMIT = 50）
const SESSION_PAGE_SIZE = 50;

function isEmojiIcon(icon?: string): boolean {
  if (!icon) return false;
  // 简单判定：单字符或典型 emoji 区间；lucide 图标名通常为英文
  return /\p{Extended_Pictographic}/u.test(icon) || [...icon].length <= 2;
}

export function SharedProjectPage({
  initialManifest,
}: {
  initialManifest: SharedProjectContentResponse;
}) {
  const { shareId } = useParams<{ shareId: string }>();
  const { t } = useTranslation();
  const { theme, toggleTheme } = useSharedPageTheme();

  const [manifest, setManifest] = useState(initialManifest);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [sessionContent, setSessionContent] = useState<
    Record<string, SharedContentResponse | "loading" | "error">
  >({});
  const pendingSessions = useRef(new Set<string>());
  const panelPrefix = useId();
  const paginationRef = useRef<HTMLDivElement>(null);
  const nextSessionFocus = useRef<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreError, setMoreError] = useState(false);
  const hasMore = computeProjectHasMore(manifest);

  const loadMore = useCallback(async () => {
    if (!shareId || loadingMore || !hasMore) return;
    const skip = manifest.sessions.length;
    paginationRef.current?.focus({ preventScroll: true });
    setLoadingMore(true);
    setMoreError(false);
    try {
      const page = await shareApi.getSharedContent(shareId, {
        sessionSkip: skip,
        sessionLimit: SESSION_PAGE_SIZE,
      });
      if (!("sessions" in page)) throw new Error("Unexpected share scope");
      nextSessionFocus.current = page.sessions[0]?.id ?? null;
      setManifest((prev) => ({
        ...prev,
        sessions: [...prev.sessions, ...page.sessions],
        sessions_total: page.sessions_total,
        has_more: page.has_more,
      }));
    } catch {
      setMoreError(true);
    } finally {
      setLoadingMore(false);
    }
  }, [shareId, manifest, loadingMore, hasMore]);

  useLayoutEffect(() => {
    if (
      nextSessionFocus.current &&
      document.activeElement === paginationRef.current
    ) {
      document
        .getElementById(`${panelPrefix}-${nextSessionFocus.current}-title`)
        ?.closest<HTMLButtonElement>("button")
        ?.focus();
    }
    nextSessionFocus.current = null;
  }, [manifest, panelPrefix]);

  const loadSession = useCallback(
    async (sessionId: string) => {
      if (!shareId || pendingSessions.current.has(sessionId)) return;
      pendingSessions.current.add(sessionId);
      setSessionContent((prev) => ({ ...prev, [sessionId]: "loading" }));
      try {
        const content = await shareApi.getSessionContentInProject(
          shareId,
          sessionId,
        );
        setSessionContent((prev) => ({ ...prev, [sessionId]: content }));
      } catch {
        setSessionContent((prev) => ({ ...prev, [sessionId]: "error" }));
      } finally {
        pendingSessions.current.delete(sessionId);
      }
    },
    [shareId],
  );

  const toggleSession = (sessionId: string) => {
    setExpanded((prev) => ({ ...prev, [sessionId]: !prev[sessionId] }));
    if (!expanded[sessionId] && !sessionContent[sessionId]) {
      void loadSession(sessionId);
    }
  };
  const owner = manifest.owner;

  const projectIcon = manifest.project.icon;

  return (
    <div className="flex flex-col bg-theme-bg text-theme-text min-h-dvh font-sans">
      {/* Header */}
      <header className="safe-area-top sticky top-0 z-40 border-b border-theme-border bg-[color-mix(in_srgb,var(--theme-bg-card)_82%,transparent)] backdrop-blur">
        <div className="max-w-4xl lg:max-w-5xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between gap-3 font-serif">
          <Link
            to="/"
            aria-label={t("share.goToChat")}
            className="inline-flex min-h-11 items-center rounded focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[var(--theme-ring)]"
          >
            <BrandWordmark decorative className="h-7 w-auto text-theme-text" />
          </Link>
          <div className="flex shrink-0 items-center gap-1.5">
            <LanguageToggle sync={false} className="!min-h-11 !min-w-11" />
            <IconButton
              size="lg"
              onClick={toggleTheme}
              aria-label={t(
                theme === "light"
                  ? "theme.switchToDark"
                  : theme === "dark"
                    ? "theme.switchToSepia"
                    : "theme.switchToLight",
              )}
              icon={
                theme === "light" ? (
                  <Moon size={18} />
                ) : theme === "dark" ? (
                  <Coffee size={18} />
                ) : (
                  <Sun size={18} />
                )
              }
            />
          </div>
        </div>
      </header>

      {/* Project cover */}
      <section className="border-b border-theme-border">
        <div className="max-w-4xl lg:max-w-5xl mx-auto px-4 sm:px-6 py-6 sm:py-10">
          <div className="flex items-start gap-3 sm:gap-4">
            <div className="flex h-11 w-11 sm:h-14 sm:w-14 shrink-0 items-center justify-center rounded-xl bg-theme-bg-subtle border border-theme-border text-24">
              {isEmojiIcon(projectIcon) ? (
                <span>{projectIcon || "📁"}</span>
              ) : (
                <Folder className="h-7 w-7 text-theme-text-secondary" />
              )}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-12 uppercase tracking-wider text-theme-text-secondary mb-1">
                {t("share.sharedProject", "分享的项目")}
              </p>
              <h1 className="text-24 sm:text-30 font-serif tracking-tight font-semibold text-balance [overflow-wrap:anywhere]">
                {manifest.project.name}
              </h1>
              <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-14 text-theme-text-secondary">
                <span className="inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap">
                  <MessageSquare size={14} aria-hidden="true" />
                  {manifest.sessions_total} {t("share.conversations", "个会话")}
                </span>
                {owner ? (
                  <span className="flex max-w-full min-w-0 items-start gap-2">
                    <span aria-hidden="true" className="shrink-0 opacity-50">
                      ·
                    </span>
                    <span className="min-w-0 [overflow-wrap:anywhere]">
                      {owner.username}
                    </span>
                  </span>
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
              const content = sessionContent[session.id];
              const panelId = `${panelPrefix}-${session.id}`;
              const titleId = `${panelId}-title`;
              return (
                <li
                  key={session.id}
                  className="rounded-xl border border-theme-border bg-theme-bg-card overflow-hidden"
                >
                  <button
                    type="button"
                    onClick={() => toggleSession(session.id)}
                    aria-expanded={isExpanded}
                    aria-controls={isExpanded ? panelId : undefined}
                    className="w-full flex items-center gap-3 px-3 sm:px-4 py-3.5 text-left hover:bg-theme-bg-subtle transition-colors motion-reduce:transition-none focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-[var(--theme-ring)]"
                  >
                    <span className="text-theme-text-secondary shrink-0">
                      {isExpanded ? (
                        <ChevronDown size={18} />
                      ) : (
                        <ChevronRight size={18} />
                      )}
                    </span>
                    <span className="flex-1 min-w-0">
                      <span
                        id={titleId}
                        className="block font-medium line-clamp-2 [overflow-wrap:anywhere]"
                      >
                        {session.name ||
                          t("share.untitledSession", "未命名会话")}
                      </span>
                      <span className="block text-12 text-theme-text-secondary truncate">
                        {session.agent_name}
                        {session.updated_at
                          ? ` · ${formatDate(session.updated_at)}`
                          : ""}
                      </span>
                    </span>
                  </button>

                  {isExpanded && (
                    <div
                      id={panelId}
                      role="region"
                      aria-labelledby={titleId}
                      tabIndex={-1}
                      className="border-t border-theme-border bg-theme-bg px-3 sm:px-6 py-4 outline-none"
                    >
                      {content === "error" ? (
                        <div className="flex flex-col items-center gap-3 py-4 text-center">
                          <p
                            role="alert"
                            className="text-14 text-theme-text-secondary"
                          >
                            {t("share.loadFailed")}
                          </p>
                          <Button
                            size="lg"
                            onClick={(event) => {
                              event.currentTarget
                                .closest<HTMLElement>('[role="region"]')
                                ?.focus({ preventScroll: true });
                              void loadSession(session.id);
                            }}
                          >
                            {t("common.retry")}
                          </Button>
                        </div>
                      ) : content && content !== "loading" ? (
                        <SessionMessages content={content} />
                      ) : (
                        <div
                          role="status"
                          className="flex items-center justify-center gap-2 py-6 text-14 text-theme-text-secondary"
                        >
                          <LoadingSpinner
                            size="sm"
                            color="text-theme-text-secondary"
                          />
                          {t("common.loading")}
                        </div>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>

          <div ref={paginationRef} tabIndex={-1} className="outline-none">
            {hasMore && (
              <div className="flex flex-col items-center gap-3 pt-4">
                {moreError && (
                  <p
                    role="alert"
                    className="text-center text-14 text-theme-text-secondary"
                  >
                    {t("share.loadFailed")}
                  </p>
                )}
                {loadingMore && (
                  <span role="status" className="sr-only">
                    {t("common.loading")}
                  </span>
                )}
                <Button size="lg" onClick={loadMore} loading={loadingMore}>
                  {moreError ? t("common.retry") : t("share.loadMore")}
                </Button>
              </div>
            )}
          </div>

          {manifest.sessions.length === 0 ? (
            <div className="text-center py-16 text-theme-text-secondary">
              {t("share.emptyProject", "项目中暂无可分享的会话")}
            </div>
          ) : null}
        </div>
      </main>

      {/* Footer */}
      <footer className="safe-area-bottom border-t border-theme-border">
        <div className="max-w-4xl lg:max-w-5xl mx-auto px-4 sm:px-6 py-6 flex items-center justify-between text-14 text-theme-text-secondary">
          <span>{APP_NAME}</span>
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex min-h-11 items-center rounded hover:text-theme-text transition-colors motion-reduce:transition-none focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[var(--theme-ring)]"
          >
            GitHub
          </a>
        </div>
      </footer>
    </div>
  );
}

function SessionMessages({ content }: { content: SharedContentResponse }) {
  const { t } = useTranslation();
  const messages = useMemo(() => {
    if (!content?.events) return [];
    return reconstructMessagesFromEvents(content.events, new Set(), {
      activeSubagentStack: [],
    });
  }, [content?.events]);

  if (messages.length === 0) {
    return (
      <p className="text-center text-theme-text-secondary py-6 text-14">
        {t("share.noMessages")}
      </p>
    );
  }

  return (
    <Suspense
      fallback={
        <div
          role="status"
          className="flex items-center justify-center gap-2 py-6 text-14 text-theme-text-secondary"
        >
          <LoadingSpinner size="sm" color="text-theme-text-secondary" />
          {t("common.loading")}
        </div>
      }
    >
      <div className="space-y-2">
        {messages.map((message, index) => (
          <div key={message.id}>
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
