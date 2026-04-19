/**
 * Search dialog for finding sessions across all projects.
 *
 * Features: fade+scale entrance, keyboard navigation
 * (↑/↓/Enter/Escape), infinite scroll, smooth scrolling.
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import { useInView } from "react-intersection-observer";
import { useTranslation } from "react-i18next";
import { Search, X, Hash } from "lucide-react";
import { sessionApi, type BackendSession } from "../../services/api";
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
  const [isAnimating, setIsAnimating] = useState(false);
  const [visible, setVisible] = useState(false);

  // ── Session state (independent pagination) ────────────────────
  const [allSessions, setAllSessions] = useState<SearchResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [skip, setSkip] = useState(0);
  const [searchQuery, setSearchQuery] = useState("");
  const [skeletonVisible, setSkeletonVisible] = useState(false);

  // Infinite scroll sentinel
  const { ref: sentinelRef, inView } = useInView({
    threshold: 0,
    rootMargin: "200px",
  });

  // ── Entrance / exit animation ──────────────────────────────────
  useEffect(() => {
    if (isOpen) {
      setIsAnimating(true);
      requestAnimationFrame(() => {
        setVisible(true);
      });
      // Reset & fetch on open
      setAllSessions([]);
      setSkip(0);
      setHasMore(false);
    } else {
      setVisible(false);
    }
  }, [isOpen]);

  const handleTransitionEnd = useCallback(() => {
    if (!visible) setIsAnimating(false);
  }, [visible]);

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
    itemRefs.current.clear();
  }, [allSessions]);

  // ── Fetch sessions (search or initial) ─────────────────────────
  const fetchSessions = useCallback(
    async (reset = false) => {
      const targetSkip = reset ? 0 : skip;
      if (!reset && (isLoadingMore || !hasMore)) return;

      if (reset) {
        setIsLoading(true);
        setSkeletonVisible(true);
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
              | string
              | null) ?? null,
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
        // silently fail
      } finally {
        setIsLoading(false);
        setIsLoadingMore(false);
        if (reset) {
          requestAnimationFrame(() => setSkeletonVisible(false));
        }
      }
    },
    [searchQuery, skip, isLoadingMore, hasMore],
  );

  // ── Fetch on open (initial load) ───────────────────────────────
  useEffect(() => {
    if (isOpen) {
      fetchSessions(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  // ── Debounced search ───────────────────────────────────────────
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout>>(null);
  useEffect(() => {
    if (!isOpen) return;
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(() => {
      fetchSessions(true);
    }, 200);
    return () => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchQuery]);

  // ── Infinite scroll trigger ────────────────────────────────────
  useEffect(() => {
    if (inView && hasMore && !isLoadingMore && !isLoading) {
      fetchSessions(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inView, hasMore, isLoadingMore, isLoading]);

  // ── Keyboard navigation ────────────────────────────────────────
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }
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

  if (!isAnimating) return null;

  return createPortal(
    <div
      className={`fixed inset-0 z-[300] flex items-center justify-center transition-all duration-200 ease-out ${
        visible ? "visible" : "invisible"
      }`}
    >
      {/* Backdrop */}
      <div
        className={`absolute inset-0 bg-black/30 transition-opacity duration-200 ${
          visible ? "opacity-100" : "opacity-0"
        }`}
        onClick={onClose}
      />

      {/* Dialog panel — scale + fade */}
      <div
        onTransitionEnd={handleTransitionEnd}
        className={`relative w-[92vw] max-w-lg bg-white dark:bg-stone-900 rounded-2xl shadow-[0_25px_60px_-12px_rgba(0,0,0,0.25)] dark:shadow-[0_25px_60px_-12px_rgba(0,0,0,0.5)] border border-stone-200/60 dark:border-stone-700/40 overflow-hidden transition-all duration-200 ease-out origin-top ${
          visible
            ? "opacity-100 scale-100 translate-y-0"
            : "opacity-0 scale-[0.97] -translate-y-2"
        }`}
      >
        {/* Search input */}
        <div className="flex items-center gap-3 px-4 py-3.5">
          <Search
            size={16}
            strokeWidth={2}
            className="flex-shrink-0 text-stone-400 dark:text-stone-500"
          />
          <input
            ref={inputRef}
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t("sidebar.searchSessions") + "..."}
            className="flex-1 min-w-0 text-[15px] bg-transparent text-stone-800 dark:text-stone-100 placeholder:text-stone-400 dark:placeholder:text-stone-500 focus:outline-none"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="flex-shrink-0 flex items-center justify-center w-5 h-5 rounded-full text-stone-400 hover:text-stone-600 dark:text-stone-500 dark:hover:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 transition-all"
            >
              <X size={12} strokeWidth={2.5} />
            </button>
          )}
          <kbd className="hidden sm:inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium text-stone-400 dark:text-stone-500 bg-stone-100 dark:bg-stone-800 rounded-md border border-stone-200/80 dark:border-stone-700/60">
            ESC
          </kbd>
        </div>

        {/* Divider */}
        <div className="mx-4 h-px bg-stone-100 dark:bg-stone-800/60" />

        {/* Results list */}
        <div
          className="h-[50vh] overflow-y-auto scroll-smooth"
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
          {/* Results area — grid stacking prevents height jump during crossfade */}
          <div className="grid h-full">
            {/* Loading state — fades out when results arrive */}
            <div
              className={`[grid-area:1/1] h-full transition-opacity duration-150 ease-out ${
                skeletonVisible
                  ? "opacity-100"
                  : "opacity-0 pointer-events-none"
              }`}
            >
              <SkeletonList
                count={5}
                className="h-full flex flex-col justify-around py-2"
                compact
              />
            </div>

            {/* Session items — fades in when skeleton fades out */}
            <div
              className={`[grid-area:1/1] transition-opacity duration-150 ease-out ${
                !isLoading ? "opacity-100" : "opacity-0 pointer-events-none"
              }`}
            >
              {/* Empty search results */}
              {hasQuery && allSessions.length === 0 && (
                <div className="px-4 py-10 text-center">
                  <p className="text-sm text-stone-400 dark:text-stone-500">
                    {t("sidebar.noSearchResults")}
                  </p>
                  <p className="mt-1 text-xs text-stone-300 dark:text-stone-600">
                    &quot;{searchQuery}&quot;
                  </p>
                </div>
              )}

              {/* Session items */}
              {allSessions.map(({ session, projectName }, index) => {
                const isActive = index === activeIndex;
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
                    <span className="flex-1 min-w-0 text-sm text-stone-700 dark:text-stone-200 truncate leading-snug">
                      {getSessionTitle(session, t)}
                    </span>
                    {projectName && (
                      <span className="flex-shrink-0 flex items-center gap-1 text-[11px] text-stone-400 dark:text-stone-500 bg-stone-100 dark:bg-stone-800/50 px-1.5 py-0.5 rounded-md">
                        <Hash size={9} strokeWidth={2} />
                        {projectName}
                      </span>
                    )}
                  </button>
                );
              })}

              {/* Infinite scroll sentinel */}
              {hasMore && (
                <div ref={sentinelRef} className="flex justify-center py-3">
                  {isLoadingMore && (
                    <div className="w-4 h-4 border-2 border-stone-300 dark:border-stone-600 border-t-stone-500 dark:border-t-stone-400 rounded-full animate-spin" />
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Bottom hint bar */}
        {!isLoading && hasQuery && allSessions.length > 0 && (
          <>
            <div className="mx-4 h-px bg-stone-100 dark:bg-stone-800/60" />
            <div className="flex items-center justify-between px-4 py-2 text-[11px] text-stone-400 dark:text-stone-500">
              <span>
                {allSessions.length} {hasMore ? "..." : ""}
              </span>
              <div className="flex items-center gap-2">
                <span className="flex items-center gap-0.5">
                  <kbd className="px-1 py-0.5 rounded bg-stone-100 dark:bg-stone-800 border border-stone-200/60 dark:border-stone-700/50 text-[10px]">
                    ↑
                  </kbd>
                  <kbd className="px-1 py-0.5 rounded bg-stone-100 dark:bg-stone-800 border border-stone-200/60 dark:border-stone-700/50 text-[10px]">
                    ↓
                  </kbd>
                  <span className="ml-0.5">{t("sidebar.navigate")}</span>
                </span>
                <span className="flex items-center gap-0.5">
                  <kbd className="px-1.5 py-0.5 rounded bg-stone-100 dark:bg-stone-800 border border-stone-200/60 dark:border-stone-700/50 text-[10px]">
                    ↵
                  </kbd>
                  <span className="ml-0.5">{t("sidebar.open")}</span>
                </span>
              </div>
            </div>
          </>
        )}
      </div>
    </div>,
    document.body,
  );
}
