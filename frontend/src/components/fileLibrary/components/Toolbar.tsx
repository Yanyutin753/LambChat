import { useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import {
  Search,
  ChevronDown,
  Star,
  X,
  Check,
  LayoutGrid,
  List,
  FolderKanban,
} from "lucide-react";
import { FILE_TYPE_FILTERS, SORT_OPTIONS } from "../constants";
import { useDropdownPos } from "../hooks/useDropdownPos";
import { DropdownShell } from "./DropdownShell";
import { SortIcon } from "./SortIcon";
import type { SortOrder, ViewMode } from "../types";

interface ToolbarProps {
  search: string;
  onSearchChange: (v: string) => void;
  activeFilter: string;
  onFilterChange: (key: string) => void;
  sortBy: string;
  sortOrder: SortOrder;
  onSortChange: (key: string, order: SortOrder) => void;
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
  favoritesOnly: boolean;
  onFavoritesToggle: () => void;
  projects: Array<{ id: string; name: string; type: string }>;
  selectedProject: string | null;
  onProjectChange: (id: string | null) => void;
}

/* ── Shared style tokens ──────────────────────────────── */

const btnBase =
  "flex items-center h-8 gap-1.5 rounded-lg border transition-all duration-150 text-[13px]";
const btnDefault =
  "border-stone-200 dark:border-stone-700/60 text-stone-500 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800/60 hover:border-stone-300 dark:hover:border-stone-600";
const btnActive =
  "border-stone-300 dark:border-stone-600 bg-stone-100 dark:bg-stone-800 text-stone-700 dark:text-stone-200";

const ddItemBase =
  "w-full text-left px-3 py-2 text-[13px] transition-colors rounded-lg flex items-center gap-2";
const ddItemActive =
  "text-stone-900 dark:text-stone-100 bg-stone-100 dark:bg-stone-700 font-medium";
const ddItemDef =
  "text-stone-500 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-stone-800/50";

const smItemBase =
  "w-full text-left px-3 py-2 text-[12px] rounded-lg flex items-center gap-2";

/* ═══════════════════════════════════════════════════════ */

export function Toolbar({
  search,
  onSearchChange,
  activeFilter,
  onFilterChange,
  sortBy,
  sortOrder,
  onSortChange,
  viewMode,
  onViewModeChange,
  favoritesOnly,
  onFavoritesToggle,
  projects,
  selectedProject,
  onProjectChange,
}: ToolbarProps) {
  const { t } = useTranslation();

  /* Dropdown positions */
  const filterDd = useDropdownPos();
  const sortDd = useDropdownPos();
  const projectDd = useDropdownPos();

  /* Dropdown visibility */
  const [showFilter, setShowFilter] = useState(false);
  const [showSort, setShowSort] = useState(false);
  const [showProject, setShowProject] = useState(false);

  const closeAll = useCallback(() => {
    setShowFilter(false);
    setShowSort(false);
    setShowProject(false);
  }, []);

  /* Derived */
  const currentFilterItem = FILE_TYPE_FILTERS.find(
    (f) => f.key === activeFilter,
  );
  const currentSortLabel = SORT_OPTIONS.find(
    (o) => o.key === sortBy && o.order === sortOrder,
  )?.labelKey;

  const selectedProjectName = selectedProject
    ? selectedProject === "none"
      ? null
      : projects.find((p) => p.id === selectedProject)?.name
    : null;

  return (
    <div className="sticky top-0 z-10">
      {/* Toolbar backdrop */}
      <div
        className="absolute inset-0"
        style={{ backgroundColor: "var(--theme-bg)" }}
      />
      <div className="absolute bottom-0 left-0 right-0 h-px bg-stone-200/60 dark:bg-stone-700/40" />

      <div className="relative px-5 md:px-6 py-3 md:py-4">
        <div className="flex items-center justify-between gap-3 w-full">
          {/* ─── Left group: Filters ─── */}
          <div className="flex flex-wrap gap-2 items-center">
            {/* Type filter */}
            <div className="relative">
              <button
                ref={filterDd.ref}
                onClick={() => {
                  closeAll();
                  setShowFilter(true);
                  setTimeout(() => filterDd.update(), 0);
                }}
                className={`${btnBase} ${btnDefault} px-2.5`}
              >
                {currentFilterItem?.icon && (
                  <currentFilterItem.icon size={14} />
                )}
                <span>
                  {t(currentFilterItem?.labelKey || "fileLibrary.types.all")}
                </span>
                <ChevronDown
                  size={14}
                  className={`text-stone-400 dark:text-stone-500 hidden md:block transition-transform duration-200 ${
                    showFilter ? "rotate-180" : ""
                  }`}
                />
              </button>
              <DropdownShell
                show={showFilter}
                onClose={() => setShowFilter(false)}
                pos={filterDd.pos}
                align="left"
                w="w-40"
              >
                {FILE_TYPE_FILTERS.map((f) => (
                  <button
                    key={f.key}
                    onClick={() => {
                      onFilterChange(f.key);
                      setShowFilter(false);
                    }}
                    className={`${ddItemBase} ${
                      activeFilter === f.key ? ddItemActive : ddItemDef
                    }`}
                  >
                    {f.icon && <f.icon size={15} />}
                    {t(f.labelKey)}
                  </button>
                ))}
              </DropdownShell>
            </div>

            {/* Favorites */}
            <button
              onClick={onFavoritesToggle}
              className={`${btnBase} px-3 transition-all duration-150 ${
                favoritesOnly
                  ? "border-amber-300/80 dark:border-amber-600/60 bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 shadow-sm shadow-amber-100 dark:shadow-black/20"
                  : "border-stone-200 dark:border-stone-700/60 text-stone-500 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800/60 hover:border-stone-300 dark:hover:border-stone-600"
              }`}
            >
              <Star
                size={14}
                className={
                  favoritesOnly ? "fill-amber-400 dark:fill-amber-500" : ""
                }
              />
              <span className="hidden md:inline">
                {t("fileLibrary.favorites", "我的收藏")}
              </span>
            </button>

            {/* Project filter */}
            {projects.length > 0 && (
              <div className="relative hidden md:block">
                <button
                  ref={projectDd.ref}
                  onClick={() => {
                    closeAll();
                    setShowProject(true);
                    setTimeout(() => projectDd.update(), 0);
                  }}
                  className={`${btnBase} px-2.5 ${
                    selectedProject ? btnActive : btnDefault
                  }`}
                >
                  <FolderKanban size={14} />
                  <span className="max-w-[72px] truncate">
                    {selectedProjectName || t("fileLibrary.projectFilter")}
                  </span>
                  <ChevronDown
                    size={14}
                    className={`text-stone-400 dark:text-stone-500 transition-transform duration-200 ${
                      showProject ? "rotate-180" : ""
                    }`}
                  />
                </button>
                <DropdownShell
                  show={showProject}
                  onClose={() => setShowProject(false)}
                  pos={projectDd.pos}
                  align="right"
                  w="w-48"
                  maxH="max-h-64"
                >
                  <button
                    onClick={() => {
                      onProjectChange(null);
                      setShowProject(false);
                    }}
                    className={`${smItemBase} ${
                      !selectedProject ? ddItemActive : ddItemDef
                    }`}
                  >
                    {t("fileLibrary.allProjects")}
                  </button>
                  <div className="mx-2 my-1 border-t border-stone-100 dark:border-stone-700" />
                  {projects.map((p) => (
                    <button
                      key={p.id}
                      onClick={() => {
                        onProjectChange(p.id);
                        setShowProject(false);
                      }}
                      className={`${smItemBase} ${
                        selectedProject === p.id ? ddItemActive : ddItemDef
                      }`}
                    >
                      <span className="truncate">{p.name}</span>
                    </button>
                  ))}
                </DropdownShell>
              </div>
            )}

            {/* Sort */}
            <div className="relative">
              <button
                ref={sortDd.ref}
                onClick={() => {
                  closeAll();
                  setShowSort(true);
                  setTimeout(() => sortDd.update(), 0);
                }}
                className={`${btnBase} gap-1 px-2 ${btnDefault}`}
              >
                <SortIcon
                  order={sortOrder}
                  className="text-stone-400 dark:text-stone-500"
                />
                <span className="max-w-[64px] truncate hidden sm:inline">
                  {t(currentSortLabel ?? "fileLibrary.sort.newest")}
                </span>
                <ChevronDown
                  size={14}
                  className={`text-stone-400 dark:text-stone-500 transition-transform duration-200 ${
                    showSort ? "rotate-180" : ""
                  }`}
                />
              </button>
              <DropdownShell
                show={showSort}
                onClose={() => setShowSort(false)}
                pos={sortDd.pos}
                align="right"
                w="w-40"
              >
                {SORT_OPTIONS.map((o, i) => {
                  const isActive = sortBy === o.key && sortOrder === o.order;
                  return (
                    <div key={`${o.key}-${o.order}`}>
                      {(i === 2 || i === 4) && (
                        <div className="mx-2 my-1 border-t border-stone-100 dark:border-stone-700" />
                      )}
                      <button
                        onClick={() => {
                          onSortChange(o.key, o.order);
                          setShowSort(false);
                        }}
                        className={`${smItemBase} ${
                          isActive ? ddItemActive : ddItemDef
                        }`}
                      >
                        <SortIcon
                          order={o.order}
                          className="shrink-0 opacity-60"
                        />
                        <span className="flex-1">{t(o.labelKey)}</span>
                        {isActive && (
                          <Check
                            size={12}
                            className="text-stone-400 dark:text-stone-500 shrink-0"
                          />
                        )}
                      </button>
                    </div>
                  );
                })}
              </DropdownShell>
            </div>
          </div>

          {/* ─── Right group: Search + View toggle ─── */}
          <div className="flex items-center gap-2 shrink-0">
            {/* Search */}
            <div className="group flex items-center gap-2.5 h-9 w-[160px] md:w-[200px] rounded-lg border border-stone-200 dark:border-stone-700/60 bg-stone-50/50 dark:bg-stone-800/30 px-3 pl-9 relative focus-within:border-stone-400 dark:focus-within:border-stone-500 focus-within:bg-white dark:focus-within:bg-stone-800/60 transition-all duration-150">
              <Search
                size={14}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-300 dark:text-stone-600 pointer-events-none"
              />
              <input
                type="text"
                value={search}
                onChange={(e) => onSearchChange(e.target.value)}
                placeholder={t("fileLibrary.searchPlaceholder")}
                className="h-full min-w-0 flex-1 bg-transparent text-[13px] text-stone-700 dark:text-stone-300 placeholder:text-stone-300 dark:placeholder:text-stone-600 focus:outline-none"
              />
              {search && (
                <button
                  onClick={() => onSearchChange("")}
                  className="shrink-0 text-stone-300 hover:text-stone-500 dark:text-stone-600 dark:hover:text-stone-400 transition-colors rounded"
                >
                  <X size={14} />
                </button>
              )}
            </div>

            {/* View toggle */}
            <div className="hidden md:block">
              <div className="flex items-center rounded-lg border border-stone-200 dark:border-stone-700/60 bg-stone-50/50 dark:bg-stone-800/30 h-8 p-px">
                {(["grid", "list"] as const).map((mode) => (
                  <button
                    key={mode}
                    onClick={() => onViewModeChange(mode)}
                    className={`relative z-10 flex items-center justify-center w-8 h-full rounded-md transition-colors duration-200 ${
                      viewMode === mode
                        ? "text-stone-800 dark:text-stone-100"
                        : "text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300"
                    }`}
                  >
                    <span className="relative z-10">
                      {mode === "grid" ? (
                        <LayoutGrid size={15} />
                      ) : (
                        <List size={15} />
                      )}
                    </span>
                    {viewMode === mode && (
                      <div className="absolute inset-0 bg-white dark:bg-stone-600 rounded-md shadow-sm dark:shadow-black/20 pointer-events-none" />
                    )}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
