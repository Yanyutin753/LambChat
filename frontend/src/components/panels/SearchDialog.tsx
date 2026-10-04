import { DialogCloseButton } from "../common/DialogCloseButton";
/**
 * Search dialog for finding sessions across all projects.
 *
 * Keyboard navigation (↑/↓/Enter/Escape) and paginated results.
 */

import {
  useEffect,
  useRef,
  useState,
  useCallback,
  useId,
  type KeyboardEvent,
} from "react";
import { flushSync } from "react-dom";
import { ModalSurface } from "../common/ModalSurface";
import { useInView } from "react-intersection-observer";
import { useTranslation } from "react-i18next";
import { Search, X, Hash } from "lucide-react";
import { sessionApi, type BackendSession } from "../../services/api";
import { PanelSearchInput } from "../common/PanelSearchInput";
import { IconButton } from "../common/ui";
import { getSessionTitle } from "./sessionHelpers";
import { SkeletonList } from "../skeletons";
import { LoadingSpinner } from "../common/LoadingSpinner";

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
  const resultsId = useId();
  const [resultsRoot, setResultsRoot] = useState<HTMLDivElement | null>(null);

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
    root: resultsRoot,
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
    setActiveIndex(-1);
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
  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.defaultPrevented || e.nativeEvent.isComposing || e.keyCode === 229)
      return;
    if (!allSessions.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      const next = activeIndex < allSessions.length - 1 ? activeIndex + 1 : 0;
      setActiveIndex(next);
      itemRefs.current.get(next)?.scrollIntoView({ block: "nearest" });
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      const next = Math.max(-1, activeIndex - 1);
      setActiveIndex(next);
      itemRefs.current.get(next)?.scrollIntoView({ block: "nearest" });
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

  const hasQuery = searchQuery.trim().length > 0;

  if (!isOpen) return null;

  return (
    <ModalSurface
      open={isOpen}
      onClose={onClose}
      label={t("sidebar.searchSessions")}
      className="modal-size-lg"
    >
      <div className="relative flex min-h-0 w-full flex-col overflow-hidden rounded-2xl border border-theme-border bg-theme-bg-card shadow-xl">
        {/* Search input */}
        <div className="flex shrink-0 items-center gap-2 px-4 pt-1 pb-2 sm:gap-3 sm:pt-4 sm:pb-3">
          <div className="flex min-w-0 flex-1 items-center gap-2 rounded-lg border border-transparent bg-theme-bg-subtle pl-3 pr-1 focus-within:border-[color-mix(in_srgb,var(--theme-ring)_55%,transparent)]">
            <Search
              size={16}
              strokeWidth={2}
              className="shrink-0 text-theme-text-tertiary"
              aria-hidden="true"
            />
            <PanelSearchInput
              ref={inputRef}
              type="text"
              role="combobox"
              aria-label={t("sidebar.searchSessions")}
              aria-autocomplete="list"
              aria-expanded="true"
              aria-controls={resultsId}
              aria-activedescendant={
                allSessions[activeIndex]
                  ? `${resultsId}-${activeIndex}`
                  : undefined
              }
              autoComplete="off"
              value={searchQuery}
              onValueChange={setSearchQuery}
              onKeyDown={handleKeyDown}
              placeholder={t("sidebar.searchSessions") + "..."}
              className="h-11 min-w-0 flex-1 border-0 bg-transparent p-0 text-16 text-theme-text placeholder:text-theme-text-tertiary outline-none focus:outline-none focus-visible:outline-none focus:ring-0"
            />
            {searchQuery && (
              <IconButton
                aria-label={t("common.clear")}
                size="sm"
                icon={<X size={14} aria-hidden="true" />}
                onClick={() => {
                  inputRef.current?.blur();
                  flushSync(() => setSearchQuery(""));
                  inputRef.current?.focus();
                }}
                className="!size-11 shrink-0"
              />
            )}
          </div>
          <DialogCloseButton onClick={onClose} />
        </div>

        {/* Results list */}
        <div
          ref={setResultsRoot}
          id={resultsId}
          role="listbox"
          aria-label={t("sidebar.searchSessions")}
          className="min-h-0 max-h-[50dvh] overflow-y-auto py-2"
          aria-busy={isLoading || isLoadingMore}
          style={{ scrollbarWidth: "thin" }}
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
                    id={`${resultsId}-${index}`}
                    type="button"
                    role="option"
                    aria-selected={isActive}
                    tabIndex={-1}
                    ref={(el) => {
                      if (el) {
                        itemRefs.current.set(index, el);
                      } else {
                        itemRefs.current.delete(index);
                      }
                    }}
                    onClick={() => onSelectSession(session.id)}
                    onMouseEnter={() => setActiveIndex(index)}
                    className={`w-full min-h-11 flex items-center gap-3 px-4 py-2.5 text-left transition-colors duration-75 motion-reduce:transition-none ${
                      isActive
                        ? "bg-theme-bg-elevated"
                        : "hover:bg-theme-bg-subtle"
                    }`}
                  >
                    <span className="flex-1 min-w-0">
                      <span
                        title={getSessionTitle(session, t)}
                        className="block text-14 font-serif text-theme-text truncate leading-snug"
                      >
                        {getSessionTitle(session, t)}
                      </span>
                      {searchMatch && (
                        <span
                          title={searchMatch}
                          className="mt-0.5 block text-12 text-theme-text-secondary truncate leading-relaxed"
                        >
                          {searchMatch}
                        </span>
                      )}
                      {projectName && (
                        <span className="mt-1 flex min-w-0 items-center gap-1 text-11 font-serif text-theme-text-tertiary">
                          <Hash
                            size={11}
                            className="shrink-0"
                            aria-hidden="true"
                          />
                          <span className="truncate" title={projectName}>
                            {projectName}
                          </span>
                        </span>
                      )}
                    </span>
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
                    <div role="status" aria-label={t("common.loading")}>
                      <LoadingSpinner
                        size="sm"
                        color="text-theme-text-secondary"
                      />
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
            <div className="mx-4 h-px shrink-0 bg-theme-border" />
            <div className="flex shrink-0 items-center justify-between gap-3 px-4 py-2 text-11 text-theme-text-tertiary">
              <span>
                {allSessions.length} {hasMore ? "..." : ""}
              </span>
              <div className="hidden sm:flex items-center gap-2">
                <span className="flex items-center gap-0.5">
                  <kbd className="px-1 py-0.5 rounded bg-theme-bg-subtle border border-theme-border text-10">
                    ↑
                  </kbd>
                  <kbd className="px-1 py-0.5 rounded bg-theme-bg-subtle border border-theme-border text-10">
                    ↓
                  </kbd>
                  <span className="ml-0.5">{t("sidebar.navigate")}</span>
                </span>
                <span className="flex items-center gap-0.5">
                  <kbd className="px-1.5 py-0.5 rounded bg-theme-bg-subtle border border-theme-border text-10">
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
