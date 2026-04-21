/**
 * 记忆空间面板 - 查看、搜索和管理记忆
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { useTranslation } from "react-i18next";
import {
  Brain,
  Trash2,
  ChevronDown,
  Check,
  X,
  Clock,
  Tag,
  RefreshCw,
  Filter,
  Eye,
} from "lucide-react";
import toast from "react-hot-toast";
import { PanelHeader } from "../common/PanelHeader";
import { Pagination } from "../common/Pagination";
import { Checkbox } from "../common/Checkbox";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { BatchActionBar } from "../panels/SkillsPanel/BatchActionBar";
import { memoryApi, type MemoryItem } from "../../services/api/memory";

const TYPE_STYLES: Record<string, string> = {
  user: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  feedback:
    "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
  project:
    "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  reference:
    "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
};

const TYPE_DOTS: Record<string, string> = {
  user: "bg-blue-500",
  feedback: "bg-amber-500",
  project: "bg-emerald-500",
  reference: "bg-purple-500",
};

const PAGE_SIZE = 20;

/* ---------- Type filter dropdown ---------- */

const TYPE_OPTIONS = [
  { value: "", labelKey: "memory.allTypes" },
  { value: "user", labelKey: "memory.type.user" },
  { value: "feedback", labelKey: "memory.type.feedback" },
  { value: "project", labelKey: "memory.type.project" },
  { value: "reference", labelKey: "memory.type.reference" },
] as const;

function TypeFilter({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node))
        setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const selected = TYPE_OPTIONS.find((o) => o.value === value);
  const dot = value ? TYPE_DOTS[value] : null;

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="inline-flex h-10 items-center gap-1.5 rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg-subtle)] px-3 text-sm text-[var(--theme-text)] transition-colors hover:bg-[var(--glass-bg-hover)]"
      >
        <Filter size={14} className="text-[var(--theme-text-secondary)]" />
        {dot && <span className={`inline-block h-2 w-2 rounded-full ${dot}`} />}
        <span>{selected ? t(selected.labelKey) : ""}</span>
        <ChevronDown
          size={14}
          className={`text-[var(--theme-text-secondary)] transition-transform ${
            open ? "rotate-180" : ""
          }`}
        />
      </button>

      {open && (
        <div className="absolute right-0 z-10 mt-1 w-40 rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg-card)] py-1 shadow-xl dark:shadow-black/40 animate-in fade-in-0 zoom-in-95 duration-100">
          {TYPE_OPTIONS.map((opt) => {
            const d = opt.value ? TYPE_DOTS[opt.value] : null;
            return (
              <button
                key={opt.value}
                onClick={() => {
                  onChange(opt.value);
                  setOpen(false);
                }}
                className={`flex w-full items-center gap-2 px-3 py-2 text-sm transition-colors ${
                  value === opt.value
                    ? "bg-[var(--theme-primary-light)] text-[var(--theme-text)]"
                    : "text-[var(--theme-text-secondary)] hover:bg-[var(--glass-bg)]"
                }`}
              >
                {d && <span className={`h-2 w-2 rounded-full ${d}`} />}
                <span className="flex-1 text-left">{t(opt.labelKey)}</span>
                {value === opt.value && (
                  <Check
                    size={14}
                    className="text-[var(--theme-text-secondary)]"
                  />
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function useRelativeTime() {
  const { t } = useTranslation();
  return (dateStr: string | null): string => {
    if (!dateStr) return "";
    const d = new Date(dateStr);
    const diffDays = Math.floor((Date.now() - d.getTime()) / 86400000);
    if (diffDays === 0)
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    if (diffDays === 1) return t("memory.timeAgo", { count: 1 });
    if (diffDays < 7) return t("memory.timeAgo", { count: diffDays });
    if (diffDays < 30)
      return t("memory.timeWeeksAgo", { count: Math.floor(diffDays / 7) });
    return t("memory.timeMonthsAgo", { count: Math.floor(diffDays / 30) });
  };
}

/* ---------- Detail modal ---------- */

function DetailModal({
  memory,
  onClose,
  onDelete,
  relativeTime,
}: {
  memory: MemoryItem;
  onClose: () => void;
  onDelete: (id: string) => void;
  relativeTime: (dateStr: string | null) => string;
}) {
  const { t } = useTranslation();
  const [content, setContent] = useState(memory.content);
  const [loading, setLoading] = useState(memory.has_full_content);

  useEffect(() => {
    if (!memory.has_full_content) return;
    let cancelled = false;
    memoryApi
      .get(memory.memory_id)
      .then(
        (full) => {
          if (!cancelled) setContent(full.content);
        },
        () => {
          if (!cancelled) setContent(memory.content);
        },
      )
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [memory]);

  const style = TYPE_STYLES[memory.memory_type] ?? TYPE_STYLES.user;

  return (
    <>
      <div
        className="modal-bottom-sheet sm:modal-centered-wrapper"
        onClick={onClose}
      />
      <div className="modal-bottom-sheet sm:modal-centered-wrapper">
        <div
          className="modal-bottom-sheet-content sm:modal-centered-content sm:max-w-2xl min-h-[40vh]"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="bottom-sheet-handle sm:hidden" />

          {/* Header */}
          <div className="flex items-start justify-between border-b border-[var(--glass-border)] p-5 sm:p-6 pb-4">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 mb-1.5">
                <span
                  className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-semibold uppercase leading-none ${style}`}
                >
                  {t(`memory.type.${memory.memory_type}`)}
                </span>
                <span className="text-[11px] text-stone-400 dark:text-stone-500">
                  {relativeTime(memory.updated_at)}
                </span>
              </div>
              <h3 className="text-lg font-semibold text-stone-900 dark:text-stone-100 font-serif truncate">
                {memory.title}
              </h3>
              {memory.created_at && (
                <p className="mt-1 text-xs text-stone-400 dark:text-stone-500 flex items-center gap-1">
                  <Clock size={12} />
                  {new Date(memory.created_at).toLocaleString()}
                  <span className="ml-2">
                    {memory.access_count ?? 0} {t("memory.accesses")}
                  </span>
                </p>
              )}
            </div>
            <div className="flex items-center gap-1 flex-shrink-0 ml-3">
              <button
                onClick={() => onDelete(memory.memory_id)}
                className="flex h-9 w-9 items-center justify-center rounded-lg text-stone-400 transition-all hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-900/30 dark:hover:text-red-400"
                title={t("common.delete")}
              >
                <Trash2 size={16} />
              </button>
              <button
                onClick={onClose}
                className="flex h-9 w-9 items-center justify-center rounded-lg text-stone-400 transition-all hover:bg-stone-100 hover:text-stone-600 dark:hover:bg-stone-800 dark:hover:text-stone-300"
              >
                <X size={20} />
              </button>
            </div>
          </div>

          {/* Tags */}
          {memory.tags.length > 0 && (
            <div className="flex items-center gap-1.5 px-5 sm:px-6 pt-3 flex-wrap">
              <Tag size={12} className="text-stone-400 flex-shrink-0" />
              {memory.tags.slice(0, 8).map((tag) => (
                <span
                  key={tag}
                  className="rounded-full bg-stone-100 px-2.5 py-0.5 text-[11px] font-medium text-stone-600 dark:bg-stone-800 dark:text-stone-400"
                >
                  {tag}
                </span>
              ))}
            </div>
          )}

          {/* Content */}
          <div className="flex-1 overflow-y-auto px-5 sm:px-6 py-4">
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <svg
                  className="h-6 w-6 animate-spin text-stone-400"
                  viewBox="0 0 24 24"
                  fill="none"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                  />
                </svg>
              </div>
            ) : (
              <div className="rounded-xl bg-stone-50 p-4 dark:bg-stone-900/60">
                <p className="text-sm text-stone-700 dark:text-stone-300 whitespace-pre-wrap leading-relaxed">
                  {content || memory.summary}
                </p>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="border-t border-[var(--glass-border)] px-5 sm:px-6 py-3">
            <button
              onClick={onClose}
              className="w-full rounded-xl bg-stone-900 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-stone-800 dark:bg-stone-100 dark:text-stone-900 dark:hover:bg-stone-200"
            >
              {t("common.close")}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

/* ---------- Delete modal ---------- */

function DeleteModal({
  onConfirm,
  onCancel,
  count = 1,
}: {
  onConfirm: () => void;
  onCancel: () => void;
  count?: number;
}) {
  const { t } = useTranslation();

  return (
    <ConfirmDialog
      isOpen
      title={t("memory.deleteConfirm")}
      message={
        count > 1
          ? t("memory.batchDeleteConfirmMessage", { count })
          : t("memory.deleteConfirmMessage")
      }
      confirmText={t("common.delete")}
      cancelText={t("common.cancel")}
      onConfirm={onConfirm}
      onCancel={onCancel}
      variant="danger"
    />
  );
}

/* ---------- Main panel ---------- */

export function MemoryPanel() {
  const { t } = useTranslation();
  const relativeTime = useRelativeTime();
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterType, setFilterType] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<MemoryItem | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set());
  const [batchLoading, setBatchLoading] = useState(false);

  const [debouncedSearch, setDebouncedSearch] = useState("");
  const searchTimer = useRef<ReturnType<typeof setTimeout>>(null);

  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(
      () => setDebouncedSearch(searchQuery),
      300,
    );
    return () => {
      if (searchTimer.current) clearTimeout(searchTimer.current);
    };
  }, [searchQuery]);

  useEffect(() => {
    setCheckedIds(new Set());
  }, [filterType, debouncedSearch, page]);

  const fetchMemories = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await memoryApi.list({
        memory_type: filterType || undefined,
        search: debouncedSearch || undefined,
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      });
      setMemories(res.memories);
      setTotal(res.total);
    } catch {
      toast.error(t("memory.fetchError"));
    } finally {
      setIsLoading(false);
    }
  }, [filterType, debouncedSearch, page, t]);

  useEffect(() => {
    fetchMemories();
  }, [fetchMemories]);

  useEffect(() => {
    setPage(1);
  }, [filterType, debouncedSearch]);

  const handleDelete = async () => {
    if (!deleteId) return;
    try {
      await memoryApi.delete(deleteId);
      toast.success(t("memory.deleted"));
      if (selected?.memory_id === deleteId) setSelected(null);
      fetchMemories();
    } catch {
      toast.error(t("memory.deleteError"));
    }
    setDeleteId(null);
  };

  const handleBatchDelete = async () => {
    if (checkedIds.size === 0) return;
    setBatchLoading(true);
    try {
      const res = await memoryApi.batchDelete(Array.from(checkedIds));
      toast.success(t("memory.batchDeleted", { count: res.deleted }));
      setCheckedIds(new Set());
      fetchMemories();
    } catch {
      toast.error(t("memory.deleteError"));
    } finally {
      setBatchLoading(false);
    }
  };

  const selectionMode = checkedIds.size > 0;
  const allChecked =
    memories.length > 0 && memories.every((m) => checkedIds.has(m.memory_id));

  const toggleCheck = (id: string) => {
    setCheckedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (allChecked) {
      setCheckedIds(new Set());
    } else {
      setCheckedIds(new Set(memories.map((m) => m.memory_id)));
    }
  };

  const clearSelection = () => setCheckedIds(new Set());

  return (
    <div className="glass-shell flex h-full flex-col min-h-0">
      <PanelHeader
        title={t("memory.title")}
        subtitle={t("memory.subtitle", { count: total })}
        icon={
          <Brain size={20} className="text-[var(--theme-text-secondary)]" />
        }
        searchValue={searchQuery}
        onSearchChange={setSearchQuery}
        searchPlaceholder={t("memory.searchPlaceholder")}
        searchAccessory={
          <TypeFilter value={filterType} onChange={setFilterType} />
        }
        actions={
          <>
            <button onClick={toggleAll} className="btn-secondary">
              <Check size={16} />
              <span className="hidden sm:inline">
                {allChecked ? t("common.deselectAll") : t("common.selectAll")}
              </span>
            </button>
            <button
              onClick={fetchMemories}
              disabled={isLoading}
              className="btn-primary"
            >
              <RefreshCw
                size={14}
                className={isLoading ? "animate-spin" : ""}
              />
              <span className="hidden sm:inline">
                {t("common.refresh", "Refresh")}
              </span>
            </button>
          </>
        }
      />

      {/* List */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-6">
        {isLoading && memories.length === 0 ? (
          <div className="flex h-40 items-center justify-center">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--theme-border)] border-t-[var(--theme-text-secondary)]" />
          </div>
        ) : !isLoading && memories.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-[var(--glass-bg)]">
              <Brain size={32} className="text-[var(--theme-text-secondary)]" />
            </div>
            <p className="text-lg font-medium text-[var(--theme-text)]">
              {searchQuery || filterType
                ? t("memory.noResults")
                : t("memory.empty")}
            </p>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {memories.map((memory) => {
              const badge = TYPE_STYLES[memory.memory_type] ?? TYPE_STYLES.user;
              const checked = checkedIds.has(memory.memory_id);
              return (
                <div
                  key={memory.memory_id}
                  className={`glass-card group relative flex flex-col rounded-xl p-4 sm:p-5 cursor-pointer transition-all duration-200 animate-glass-enter ${
                    checked ? "ring-2 ring-[var(--theme-primary)]" : ""
                  }`}
                  onClick={() => !selectionMode && setSelected(memory)}
                >
                  {/* Checkbox */}
                  <div
                    className={`absolute top-3 right-3 z-10 transition-all duration-200 ${
                      checked ? "scale-110" : "scale-90 group-hover:scale-100"
                    }`}
                  >
                    <Checkbox
                      size="lg"
                      checked={checked}
                      onChange={() => toggleCheck(memory.memory_id)}
                      className="shadow-sm opacity-0 group-hover:opacity-100"
                    />
                  </div>

                  {/* Header */}
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2 mb-2">
                      <span
                        className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium ${badge}`}
                      >
                        {t(`memory.type.${memory.memory_type}`)}
                      </span>
                      <span className="text-[11px] text-[var(--theme-text-secondary)]">
                        {memory.updated_at
                          ? new Date(memory.updated_at).toLocaleString([], {
                              year: "numeric",
                              month: "short",
                              day: "numeric",
                              hour: "2-digit",
                              minute: "2-digit",
                            })
                          : ""}
                      </span>
                    </div>

                    <h4 className="truncate text-base font-semibold text-[var(--theme-text)] pr-8">
                      {memory.title}
                    </h4>

                    <p className="mt-1 text-sm leading-relaxed text-[var(--theme-text-secondary)] line-clamp-2">
                      {memory.summary}
                    </p>
                  </div>

                  {/* Tags */}
                  {memory.tags.length > 0 && (
                    <div className="my-3 flex flex-wrap gap-1.5">
                      {memory.tags.slice(0, 3).map((tag) => (
                        <span key={tag} className="glass-tag glass-tag--accent">
                          {tag}
                        </span>
                      ))}
                      {memory.tags.length > 3 && (
                        <span className="glass-tag glass-tag--overflow">
                          +{memory.tags.length - 3}
                        </span>
                      )}
                    </div>
                  )}

                  {/* Footer */}
                  <div className="mt-auto flex items-center gap-2 border-t border-[var(--glass-border)] pt-3 mt-3.5">
                    <div className="inline-flex items-center gap-1.5 rounded-full bg-[var(--glass-bg)] px-2 py-0.5 text-[11px] text-[var(--theme-text-secondary)]">
                      <Eye size={12} />
                      {memory.access_count ?? 0} {t("memory.accesses")}
                    </div>

                    <div className="ml-auto" />

                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setDeleteId(memory.memory_id);
                      }}
                      className="btn-icon inline-flex h-8 w-8 items-center justify-center rounded-lg text-[var(--theme-text-secondary)] transition-colors hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/30 dark:hover:text-red-400"
                      title={t("common.delete")}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Pagination */}
      {total > PAGE_SIZE && (
        <div className="glass-divider bg-transparent px-4 py-4 sm:px-6">
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={total}
            onChange={setPage}
          />
        </div>
      )}

      {/* Detail modal */}
      {selected && (
        <DetailModal
          memory={selected}
          onClose={() => setSelected(null)}
          onDelete={setDeleteId}
          relativeTime={relativeTime}
        />
      )}

      {/* Delete modal */}
      {deleteId && (
        <DeleteModal
          onConfirm={handleDelete}
          onCancel={() => setDeleteId(null)}
        />
      )}

      {selectionMode && (
        <BatchActionBar
          selectedCount={checkedIds.size}
          batchLoading={batchLoading}
          onBatchToggle={() => {}}
          onBatchDelete={handleBatchDelete}
          onClearSelection={clearSelection}
        />
      )}
    </div>
  );
}
