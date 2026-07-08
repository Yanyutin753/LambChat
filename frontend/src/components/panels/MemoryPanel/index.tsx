import {
  useState,
  useEffect,
  useCallback,
  useRef,
  type ChangeEvent,
} from "react";
import { useTranslation } from "react-i18next";
import {
  Brain,
  Trash2,
  Check,
  RefreshCw,
  Download,
  Upload,
  Plus,
  Pencil,
  Eye,
} from "lucide-react";
import toast from "react-hot-toast";
import { PanelHeader } from "../../common/PanelHeader";
import { Pagination } from "../../common/Pagination";
import { MemoryPanelSkeleton } from "../../skeletons";
import { Checkbox } from "../../common/Checkbox";
import { Button, IconButton } from "../../common";
import { BatchActionBar } from "../SkillsPanel/BatchActionBar";
import { memoryApi, type MemoryItem } from "../../../services/api/memory";
import {
  TYPE_STYLES,
  SOURCE_STYLES,
  SOURCE_DOTS,
  PAGE_SIZE,
} from "./constants";
import { useRelativeTime } from "./useRelativeTime";
import { formatDateTimeShort } from "../../../utils/datetime";
import { MemoryFilter } from "./MemoryFilter";
import { MemoryEditor } from "./MemoryEditor";
import { DetailModal } from "./DetailModal";
import { DeleteModal } from "./DeleteModal";
import { useSettingsContext } from "../../../contexts/SettingsContext";

export function MemoryPanel() {
  const { t } = useTranslation();
  const { enableMemory } = useSettingsContext();
  const relativeTime = useRelativeTime();
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterType, setFilterType] = useState("");
  const [filterSource, setFilterSource] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<MemoryItem | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set());
  const [batchLoading, setBatchLoading] = useState(false);
  const [exportLoading, setExportLoading] = useState(false);
  const [importLoading, setImportLoading] = useState(false);
  const [editingMemory, setEditingMemory] = useState<
    MemoryItem | null | undefined
  >(undefined);
  // undefined = closed, null = create new, MemoryItem = edit existing

  const [debouncedSearch, setDebouncedSearch] = useState("");
  const searchTimer = useRef<ReturnType<typeof setTimeout>>(null);
  const importInputRef = useRef<HTMLInputElement>(null);

  const handleSearchQueryChange = useCallback((query: string) => {
    setPage(1);
    setSearchQuery(query);
  }, []);
  const handleFilterTypeChange = useCallback((type: string) => {
    setPage(1);
    setFilterType(type);
  }, []);
  const handleFilterSourceChange = useCallback((source: string) => {
    setPage(1);
    setFilterSource(source);
  }, []);

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
  }, [filterType, filterSource, debouncedSearch, page]);

  const fetchMemories = useCallback(async () => {
    if (!enableMemory) {
      setMemories([]);
      setTotal(0);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    try {
      const res = await memoryApi.list({
        memory_type: filterType || undefined,
        source: filterSource || undefined,
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
  }, [enableMemory, filterType, filterSource, debouncedSearch, page, t]);

  useEffect(() => {
    fetchMemories();
  }, [fetchMemories]);

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

  const handleExport = async () => {
    setExportLoading(true);
    try {
      const data = await memoryApi.export();
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      const date = new Date().toISOString().slice(0, 10);
      link.href = url;
      link.download = `lambchat-memory-${date}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      toast.success(t("memory.exportSuccess", { count: data.memories.length }));
    } catch {
      toast.error(t("memory.exportError"));
    } finally {
      setExportLoading(false);
    }
  };

  const handleImportClick = () => {
    importInputRef.current?.click();
  };

  const handleImportFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    setImportLoading(true);
    try {
      const text = await file.text();
      const data = JSON.parse(text);
      const result = await memoryApi.import(data);
      toast.success(
        t("memory.importSuccess", {
          imported: result.imported,
          created: result.created,
          overwritten: result.overwritten,
        }),
      );
      await fetchMemories();
    } catch {
      toast.error(t("memory.importError"));
    } finally {
      setImportLoading(false);
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

  if (isLoading && memories.length === 0) {
    return <MemoryPanelSkeleton />;
  }

  return (
    <div className="glass-shell flex h-full flex-col min-h-0">
      <PanelHeader
        title={t("memory.title")}
        subtitle={t("memory.subtitle", { count: total })}
        icon={
          <Brain size={20} className="text-[var(--theme-text-secondary)]" />
        }
        searchValue={searchQuery}
        onSearchChange={handleSearchQueryChange}
        searchPlaceholder={t("memory.searchPlaceholder")}
        searchAccessory={
          <MemoryFilter
            typeValue={filterType}
            typeOnChange={handleFilterTypeChange}
            sourceValue={filterSource}
            sourceOnChange={handleFilterSourceChange}
          />
        }
        actions={
          enableMemory ? (
            <>
              <Button
                variant="primary"
                onClick={() => setEditingMemory(null)}
                leftIcon={<Plus size={16} />}
                title={t("memory.createTitle")}
              >
                <span className="hidden sm:inline">
                  {t("memory.createBtn")}
                </span>
              </Button>
              <Button
                onClick={handleImportClick}
                disabled={importLoading}
                leftIcon={
                  <Upload
                    size={16}
                    className={importLoading ? "animate-pulse" : ""}
                  />
                }
                title={t("memory.import")}
              >
                <span className="hidden sm:inline">{t("memory.import")}</span>
              </Button>
              <Button
                onClick={handleExport}
                disabled={exportLoading}
                leftIcon={
                  <Download
                    size={16}
                    className={exportLoading ? "animate-pulse" : ""}
                  />
                }
                title={t("memory.export")}
              >
                <span className="hidden sm:inline">{t("memory.export")}</span>
              </Button>
              <Button onClick={toggleAll} leftIcon={<Check size={16} />}>
                <span className="hidden sm:inline">
                  {allChecked
                    ? t("common.deselectAll")
                    : t("common.selectAll")}
                </span>
              </Button>
              <Button
                variant="primary"
                onClick={fetchMemories}
                disabled={isLoading}
                leftIcon={
                  <RefreshCw
                    size={14}
                    className={isLoading ? "animate-spin" : ""}
                  />
                }
              >
                <span className="hidden sm:inline">
                  {t("common.refresh", "Refresh")}
                </span>
              </Button>
            </>
          ) : null
        }
      />

      <input
        ref={importInputRef}
        type="file"
        accept="application/json,.json"
        className="hidden"
        onChange={handleImportFile}
      />

      {/* List */}
      <div className="flex-1 overflow-y-auto py-2 sm:py-4 px-4 sm:p-6">
        {!enableMemory ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-[var(--glass-bg)]">
              <Brain size={32} className="text-[var(--theme-text-secondary)]" />
            </div>
            <p className="text-lg font-medium text-[var(--theme-text)]">
              {t("memory.title")}
            </p>
            <p className="mt-2 max-w-md text-sm leading-relaxed text-[var(--theme-text-secondary)]">
              {t(
                "memory.disabledHint",
                "Memory is disabled in System Settings. Stored memories are preserved, but memory actions are unavailable until ENABLE_MEMORY is turned on.",
              )}
            </p>
          </div>
        ) : isLoading && memories.length === 0 ? (
          <MemoryPanelSkeleton />
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
          <div className="grid gap-3 auto-grid-cols">
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
                      <span
                        className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${
                          SOURCE_STYLES[memory.source] ?? SOURCE_STYLES.manual
                        }`}
                      >
                        <span
                          className={`h-1.5 w-1.5 rounded-full ${
                            SOURCE_DOTS[memory.source] ?? SOURCE_DOTS.manual
                          }`}
                        />
                        {t(`memory.source.${memory.source}`, memory.source)}
                      </span>
                      <span className="text-[11px] text-[var(--theme-text-secondary)]">
                        {memory.updated_at
                          ? formatDateTimeShort(memory.updated_at)
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
                        <span key={tag} className="es-chip">
                          {tag}
                        </span>
                      ))}
                      {memory.tags.length > 3 && (
                        <span className="es-chip">
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

                    <IconButton
                      aria-label={t("common.edit")}
                      icon={<Pencil size={14} />}
                      onClick={(e) => {
                        e.stopPropagation();
                        setEditingMemory(memory);
                      }}
                      size="sm"
                      className="h-8 w-8 rounded-lg text-[var(--theme-text-secondary)] hover:bg-blue-50 hover:text-blue-600 dark:hover:bg-blue-900/30 dark:hover:text-blue-400"
                      title={t("common.edit")}
                    />
                    <IconButton
                      aria-label={t("common.delete")}
                      icon={<Trash2 size={14} />}
                      onClick={(e) => {
                        e.stopPropagation();
                        setDeleteId(memory.memory_id);
                      }}
                      size="sm"
                      className="h-8 w-8 rounded-lg text-[var(--theme-text-secondary)] hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/30 dark:hover:text-red-400"
                      title={t("common.delete")}
                    />
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
          onEdit={(mem) => {
            setSelected(null);
            setEditingMemory(mem);
          }}
          relativeTime={relativeTime}
        />
      )}

      {/* Memory editor (create / edit) */}
      {editingMemory !== undefined && (
        <MemoryEditor
          memory={editingMemory}
          onClose={() => setEditingMemory(undefined)}
          onSaved={fetchMemories}
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
