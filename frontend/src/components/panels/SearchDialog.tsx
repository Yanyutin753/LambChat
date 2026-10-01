/**
 * Search dialog for finding sessions across all projects.
 *
 * Keyboard navigation (↑/↓/Enter/Escape) and paginated results.
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { flushSync } from "react-dom";
import { ModalSurface } from "../common/ModalSurface";
import { useInView } from "react-intersection-observer";
import { useTranslation } from "react-i18next";
import { Search, X, Hash } from "lucide-react";
import { sessionApi, type BackendSession } from "../../services/api";
import { PanelSearchInput } from "../common/PanelSearchInput";
import { Button, IconButton } from "../common/ui";
import { getSessionTitle } from "./sessionHelpers";
import { SkeletonList } from "../skeletons";

const PAGE_SIZE = 30;

interface SearchResult {
  session: BackendSession;
  projectName: string | null;
}

interface SearchDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectSession: (sessionId: string) => void;
}

export function SearchDialog({
  isOpen,
  onClose,
  onSelectSession,
}: SearchDialogProps) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const itemRefs = useRef<Map<number, HTMLButtonElement>>(new Map());
  const [activeIndex, setActiveIndex] = useState(-1);

  // ── Session state (independent pagination) ────────────────────
  const [allSessions, setAllSessions] = useState<SearchResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [skip, setSkip] = useState(0);
  const [searchQuery, setSearchQuery] = useState("");
  const [hasError, setHasError] = useState(false);
  const requestIdRef = useRef(0);
  const retryResetRef = useRef(true);

  // Infinite scroll sentinel
  const { ref: sentinelRef, inView } = useInView({
    threshold: 0,
    rootMargin: "200px",
  });

  // ── Focus input on open ────────────────────────────────────────
  useEffect(() => {
    if (isOpen) {
      const timer = setTimeout(() => inputRef.current?.focus(), 60);
      return () => clearTimeout(timer);
    }
  }, [isOpen]);

  // ── Reset active index when results change ─────────────────────
  useEffect(() => {
    setActiveIndex(-1);
  }, [allSessions]);

  // ── Fetch sessions (search or initial) ─────────────────────────
  const fetchSessions = useCallback(
    async (reset = false) => {
      const targetSkip = reset ? 0 : skip;
      if (!reset && (isLoadingMore || !hasMore)) return;
      const requestId = ++requestIdRef.current;
      setHasError(false);

      if (reset) {
        setIsLoading(true);
      } else {
        setIsLoadingMore(true);
      }

      try {
        const q = searchQuery.trim();
        const response = await sessionApi.list({
          limit: PAGE_SIZE,
          skip: targetSkip,
          status: "active",
          ...(q ? { search: q } : {}),
        });
        if (requestId !== requestIdRef.current) return;

        const newSessions =
          "sessions" in response
            ? response.sessions
            : Array.isArray(response)
              ? response
              : [];
        const newHasMore = "has_more" in response ? response.has_more : false;

        // Map to SearchResult (no project info from global search)
        const results: SearchResult[] = newSessions.map((s) => ({
          session: s,
          projectName:
            ((s.metadata as Record<string, unknown>)?.project_name as
              string | null) ?? null,
        }));

        if (reset) {
          setAllSessions(results);
          setSkip(results.length);
        } else {
          setAllSessions((prev) => [...prev, ...results]);
          setSkip(targetSkip + results.length);
        }
        setHasMore(newSessions.length > 0 ? newHasMore : false);
      } catch {
        if (requestId === requestIdRef.current) {
          retryResetRef.current = reset;
          setHasError(true);
        }
      } finally {
        if (requestId === requestIdRef.current) {
          setIsLoading(false);
          setIsLoadingMore(false);
        }
      }
    },
    [searchQuery, skip, isLoadingMore, hasMore],
  );

  // Invalidate old queries immediately, including the debounce window and close.
  useEffect(() => {
    const requests = requestIdRef;
    ++requests.current;
    if (!isOpen) return;
    setIsLoading(true);
    setIsLoadingMore(false);
    setHasError(false);
    setAllSessions([]);
    setHasMore(false);
    const timer = setTimeout(() => {
      fetchSessions(true);
    }, 200);
    return () => {
      clearTimeout(timer);
      ++requests.current;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, searchQuery]);

  // ── Infinite scroll trigger ────────────────────────────────────
  useEffect(() => {
    if (inView && hasMore && !isLoadingMore && !isLoading && !hasError) {
      fetchSessions(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inView, hasMore, isLoadingMore, isLoading, hasError]);

  // ── Keyboard navigation ────────────────────────────────────────
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        e.defaultPrevented ||
        e.isComposing ||
        e.keyCode === 229 ||
        e.target !== inputRef.current
      )
        return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIndex((prev) => {
          const next = prev < allSessions.length - 1 ? prev + 1 : 0;
          itemRefs.current.get(next)?.scrollIntoView({ block: "nearest" });
          return next;
        });
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIndex((prev) => {
          if (prev <= 0) {
            inputRef.current?.focus();
            return -1;
          }
          const next = prev - 1;
          itemRefs.current.get(next)?.scrollIntoView({ block: "nearest" });
          return next;
        });
        return;
      }
      if (e.key === "Enter") {
        if (activeIndex >= 0 && activeIndex < allSessions.length) {
          e.preventDefault();
          onSelectSession(allSessions[activeIndex].session.id);
        }
        return;
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, activeIndex, allSessions, onClose, onSelectSession]);

  const hasQuery = searchQuery.trim().length > 0;

  if (!isOpen) return null;

  return (
    <ModalSurface
      open={isOpen}
      onClose={onClose}
      label={t("sidebar.searchSessions")}
    >
      <div className="relative w-[92vw] max-w-lg bg-theme-bg-card dark:bg-stone-900 rounded-2xl shadow-[0_25px_60px_-12px_rgba(0,0,0,0.25)] dark:shadow-[0_25px_60px_-12px_rgba(0,0,0,0.5)] border border-stone-200/60 dark:border-stone-700/40 overflow-hidden ">
        {/* Search input */}
        <div className="flex items-center gap-2 sm:gap-3 px-4 py-3.5">
          <Search
            size={16}
            strokeWidth={2}
            className="flex-shrink-0 text-stone-400 dark:text-stone-500"
          />
          <PanelSearchInput
            ref={inputRef}
            type="text"
            aria-label={t("sidebar.searchSessions")}
            value={searchQuery}
            onValueChange={setSearchQuery}
            placeholder={t("sidebar.searchSessions") + "..."}
            className="flex-1 min-w-0 text-15 bg-transparent text-stone-800 dark:text-stone-100 placeholder:text-stone-400 dark:placeholder:text-stone-500 focus:outline-none"
          />
          <div className="flex shrink-0 items-center gap-0">
            {searchQuery && (
              <IconButton
                aria-label={t("common.clear")}
                size="lg"
                icon={<X size={12} strokeWidth={2.5} />}
                onClick={() => {
                  flushSync(() => setSearchQuery(""));
                  inputRef.current?.focus();
                }}
                className="sm:!size-5"
              />
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={onClose}
              className="!min-h-11 sm:hidden"
            >
              {t("common.cancel")}
            </Button>
          </div>
          <kbd className="hidden sm:inline-flex items-center px-1.5 py-0.5 text-10 font-medium font-serif text-stone-400 dark:text-stone-500 bg-stone-100 dark:bg-stone-800 rounded-md border border-stone-200/80 dark:border-stone-700/60">
            ESC
          </kbd>
        </div>

        {/* Divider */}
        <div className="mx-4 h-px bg-stone-100 dark:bg-stone-800/60" />

        {/* Results list */}
        <div
          className="max-h-[50dvh] overflow-y-auto py-2"
          aria-busy={isLoading || isLoadingMore}
          style={{
            scrollbarWidth: "thin",
            scrollbarColor: "transparent transparent",
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLDivElement).style.scrollbarColor =
              "rgba(168,162,158,0.3) transparent";
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLDivElement).style.scrollbarColor =
              "transparent transparent";
          }}
        >
          {isLoading ? (
            <SkeletonList count={5} className="py-2" compact />
          ) : (
            <div>
              {/* Empty search results */}
              {!hasError && allSessions.length === 0 && (
                <div
                  role="status"
                  className="flex flex-col items-center justify-center px-4 py-8 text-center"
                >
                  <p className="text-14 text-theme-text-secondary">
                    {t(
                      hasQuery
                        ? "sidebar.noSearchResults"
                        : "sidebar.noSessions",
                    )}
                  </p>
                  {hasQuery && (
                    <p className="mt-1 max-w-full break-words text-12 text-theme-text-tertiary">
                      &quot;{searchQuery}&quot;
                    </p>
                  )}
                </div>
              )}

              {/* Session items */}
              {allSessions.map(({ session, projectName }, index) => {
                const isActive = index === activeIndex;
                const searchMatch =
                  typeof (session.metadata as Record<string, unknown>)
                    ?.search_match === "string"
                    ? ((session.metadata as Record<string, unknown>)
                        .search_match as string)
                    : null;
                return (
                  <button
                    key={session.id}
                    ref={(el) => {
                      if (el) {
                        itemRefs.current.set(index, el);
                      } else {
                        itemRefs.current.delete(index);
                      }
                    }}
                    onClick={() => onSelectSession(session.id)}
                    onMouseEnter={() => setActiveIndex(index)}
                    className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition-all duration-75 group ${
                      isActive
                        ? "bg-stone-100 dark:bg-stone-800/60"
                        : "hover:bg-stone-50 dark:hover:bg-stone-800/30"
                    }`}
                  >
                    <span className="flex-1 min-w-0">
                      <span className="block text-14 font-serif text-stone-700 dark:text-stone-200 truncate leading-snug">
                        {getSessionTitle(session, t)}
                      </span>
                      {searchMatch && (
                        <span
                          title={searchMatch}
                          className="mt-0.5 block text-12 text-stone-400 dark:text-stone-500 truncate leading-relaxed"
                        >
                          {searchMatch}
                        </span>
                      )}
                    </span>
                    {projectName && (
                      <span className="flex-shrink-0 flex items-center gap-1 text-11 font-serif text-stone-400 dark:text-stone-500 bg-stone-100 dark:bg-stone-800/50 px-1.5 py-0.5 rounded-md">
                        <Hash size={9} strokeWidth={2} />
                        {projectName}
                      </span>
                    )}
                  </button>
                );
              })}

              {hasError && (
                <div
                  role="alert"
                  className="flex flex-col items-center gap-3 px-4 py-6 text-center"
                >
                  <p className="text-14 text-theme-text-secondary">
                    {t("session.loadFailed")}
                  </p>
                  <button
                    type="button"
                    onClick={() => {
                      inputRef.current?.focus();
                      void fetchSessions(retryResetRef.current);
                    }}
                    className="min-h-11 rounded-lg px-4 text-14 text-theme-text hover:bg-theme-bg-elevated focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)]"
                  >
                    {t("sidebar.retry")}
                  </button>
                </div>
              )}
              {/* Infinite scroll sentinel */}
              {hasMore && !hasError && (
                <div ref={sentinelRef} className="flex justify-center py-3">
                  {isLoadingMore && (
                    <div className="relative w-4 h-4">
                      <div className="absolute inset-0 rounded-full border-2 border-stone-200 dark:border-stone-700" />
                      <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-stone-500 dark:border-t-stone-400 animate-spin will-change-transform" />
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Bottom hint bar */}
        {!isLoading && hasQuery && allSessions.length > 0 && (
          <>
            <div className="mx-4 h-px bg-stone-100 dark:bg-stone-800/60" />
            <div className="flex items-center justify-between px-4 py-2 text-11 text-stone-400 dark:text-stone-500">
              <span>
                {allSessions.length} {hasMore ? "..." : ""}
              </span>
              <div className="flex items-center gap-2">
                <span className="flex items-center gap-0.5">
                  <kbd className="px-1 py-0.5 rounded bg-stone-100 dark:bg-stone-800 border border-stone-200/60 dark:border-stone-700/50 text-10">
                    ↑
                  </kbd>
                  <kbd className="px-1 py-0.5 rounded bg-stone-100 dark:bg-stone-800 border border-stone-200/60 dark:border-stone-700/50 text-10">
                    ↓
                  </kbd>
                  <span className="ml-0.5">{t("sidebar.navigate")}</span>
                </span>
                <span className="flex items-center gap-0.5">
                  <kbd className="px-1.5 py-0.5 rounded bg-stone-100 dark:bg-stone-800 border border-stone-200/60 dark:border-stone-700/50 text-10">
                    ↵
                  </kbd>
                  <span className="ml-0.5">{t("sidebar.open")}</span>
                </span>
              </div>
            </div>
          </>
        )}
      </div>
    </ModalSurface>
  );
}
