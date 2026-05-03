import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  UserRound,
  Plus,
  Copy,
  Pencil,
  Check,
  X,
  Trash2,
  Users,
  User,
  Sparkles,
  Tag,
  ChevronDown,
  Save,
} from "lucide-react";
import { PanelHeader } from "../common/PanelHeader";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { PersonaPlazaSkeleton } from "../skeletons";
import { useAuth } from "../../hooks/useAuth";
import { usePersonaPresets } from "../../hooks/usePersonaPresets";
import { useSwipeToClose } from "../../hooks/useSwipeToClose";
import type { PersonaPreset } from "../../types";
import { Permission } from "../../types";

const SESSION_CONFIG_KEY = "lambchat_session_config";

function readPersonaPresetId(): string | null {
  try {
    const raw = localStorage.getItem(SESSION_CONFIG_KEY);
    if (!raw) return null;
    return JSON.parse(raw)?.personaPresetId || null;
  } catch {
    return null;
  }
}

const GRADIENT_PALETTES = [
  ["#8b5cf6", "#7c3aed", "#6d28d9"],
  ["#3b82f6", "#2563eb", "#1d4ed8"],
  ["#f43f5e", "#e11d48", "#be123c"],
  ["#f59e0b", "#d97706", "#b45309"],
  ["#10b981", "#059669", "#047857"],
  ["#6366f1", "#4f46e5", "#4338ca"],
  ["#ec4899", "#db2777", "#be185d"],
  ["#0ea5e9", "#0284c7", "#0369a1"],
  ["#14b8a6", "#0d9488", "#0f766e"],
  ["#f97316", "#ea580c", "#c2410c"],
  ["#a855f7", "#9333ea", "#7e22ce"],
  ["#22d3ee", "#06b6d4", "#0891b2"],
];

function nameToGradient(name: string) {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  return GRADIENT_PALETTES[Math.abs(hash) % GRADIENT_PALETTES.length];
}

type ScopeFilter = "all" | "global" | "user";

export function PersonaPlazaPanel() {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const canRead = hasPermission(Permission.PERSONA_PRESET_READ);
  const canWrite = hasPermission(Permission.PERSONA_PRESET_WRITE);

  const {
    presets,
    isLoading,
    isMutating,
    usePreset,
    copyPreset,
    createPreset,
    updatePreset,
    deletePreset,
  } = usePersonaPresets({ enabled: canRead });

  const [query, setQuery] = useState("");
  const [activeTag, setActiveTag] = useState<string | null>(null);
  const [scopeFilter, setScopeFilter] = useState<ScopeFilter>("all");
  const [selectedPresetId, setSelectedPresetId] = useState<string | null>(null);

  const [showModal, setShowModal] = useState(false);
  const [editingPreset, setEditingPreset] = useState<PersonaPreset | null>(
    null,
  );
  const [draft, setDraft] = useState({
    name: "",
    description: "",
    system_prompt: "",
    tags: "",
    skill_names: "",
  });

  const [deleteTarget, setDeleteTarget] = useState<PersonaPreset | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isFilterOpen, setIsFilterOpen] = useState(false);

  const closeModal = useCallback(() => {
    setShowModal(false);
    setEditingPreset(null);
  }, []);
  const modalRef = useSwipeToClose({ onClose: closeModal });

  useEffect(() => {
    setSelectedPresetId(readPersonaPresetId());
  }, []);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (isFilterOpen && !target.closest("[data-persona-filter]")) {
        setIsFilterOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [isFilterOpen]);

  const allTags = useMemo(
    () => Array.from(new Set(presets.flatMap((p) => p.tags))).sort(),
    [presets],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return presets.filter((preset) => {
      const matchesQuery =
        !q ||
        preset.name.toLowerCase().includes(q) ||
        preset.description.toLowerCase().includes(q) ||
        preset.system_prompt.toLowerCase().includes(q);
      const matchesTag = !activeTag || preset.tags.includes(activeTag);
      const matchesScope =
        scopeFilter === "all" || preset.scope === scopeFilter;
      return matchesQuery && matchesTag && matchesScope;
    });
  }, [presets, query, activeTag, scopeFilter]);

  const globalCount = useMemo(
    () => presets.filter((p) => p.scope === "global").length,
    [presets],
  );
  const userCount = useMemo(
    () => presets.filter((p) => p.scope === "user").length,
    [presets],
  );

  const handleUse = useCallback(
    async (preset: PersonaPreset) => {
      const snapshot = await usePreset(preset.id);
      if (snapshot) {
        setSelectedPresetId(preset.id);
        try {
          const raw = localStorage.getItem(SESSION_CONFIG_KEY);
          const existing = raw ? JSON.parse(raw) : {};
          localStorage.setItem(
            SESSION_CONFIG_KEY,
            JSON.stringify({
              ...existing,
              personaPresetId: preset.id,
              personaSnapshot: snapshot,
            }),
          );
        } catch {}
      }
    },
    [usePreset],
  );

  const handleClear = useCallback(() => {
    setSelectedPresetId(null);
    try {
      const raw = localStorage.getItem(SESSION_CONFIG_KEY);
      const existing = raw ? JSON.parse(raw) : {};
      localStorage.setItem(
        SESSION_CONFIG_KEY,
        JSON.stringify({
          ...existing,
          personaPresetId: null,
          personaSnapshot: null,
        }),
      );
    } catch {}
  }, []);

  const handleCopy = useCallback(
    async (preset: PersonaPreset) => {
      await copyPreset(preset.id);
    },
    [copyPreset],
  );

  const openModal = (preset: PersonaPreset | null) => {
    setEditingPreset(preset);
    setDraft({
      name: preset?.name || "",
      description: preset?.description || "",
      system_prompt: preset?.system_prompt || "",
      tags: preset?.tags.join(", ") || "",
      skill_names: preset?.skill_names.join(", ") || "",
    });
    setShowModal(true);
  };

  const handleSave = useCallback(async () => {
    if (!draft.name.trim() || !draft.system_prompt.trim()) return;
    const data = {
      name: draft.name.trim(),
      description: draft.description.trim() || undefined,
      system_prompt: draft.system_prompt.trim(),
      tags: draft.tags
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      skill_names: draft.skill_names
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    };
    if (editingPreset) {
      await updatePreset(editingPreset.id, data);
    } else {
      await createPreset(data);
    }
    closeModal();
  }, [draft, editingPreset, createPreset, updatePreset, closeModal]);

  const handleDelete = useCallback(async () => {
    if (!deleteTarget) return;
    setIsDeleting(true);
    const ok = await deletePreset(deleteTarget.id);
    setIsDeleting(false);
    if (ok && selectedPresetId === deleteTarget.id) handleClear();
    setDeleteTarget(null);
  }, [deleteTarget, deletePreset, selectedPresetId, handleClear]);

  const toggleTag = (tag: string) =>
    setActiveTag((prev) => (prev === tag ? null : tag));
  const clearFilters = () => {
    setActiveTag(null);
    setQuery("");
  };

  const scopeTabs = [
    {
      key: "all" as ScopeFilter,
      label: t("personaPresets.all", "全部"),
      icon: Users,
      count: presets.length,
    },
    {
      key: "global" as ScopeFilter,
      label: t("personaPresets.official", "官方"),
      icon: Sparkles,
      count: globalCount,
    },
    {
      key: "user" as ScopeFilter,
      label: t("personaPresets.mine", "我的"),
      icon: User,
      count: userCount,
    },
  ];

  const isFormValid = draft.name.trim() && draft.system_prompt.trim();
  const hasActiveFilters = !!activeTag || query.length > 0;

  if (isLoading) return <PersonaPlazaSkeleton />;

  return (
    <div className="skill-theme-shell flex h-full min-h-0 flex-col">
      <PanelHeader
        className="skill-panel-header"
        title={t("personaPresets.title", "角色广场")}
        subtitle={t("personaPresets.subtitle", "选择一个角色开始对话")}
        icon={
          <UserRound size={18} className="text-stone-600 dark:text-stone-400" />
        }
        searchValue={query}
        onSearchChange={setQuery}
        searchPlaceholder={t("personaPresets.search", "搜索角色名称、描述...")}
        searchAccessory={
          allTags.length > 0 ? (
            <div className="relative shrink-0" data-persona-filter>
              <button
                type="button"
                onClick={() => setIsFilterOpen((prev) => !prev)}
                className={`btn-secondary h-10 px-3 ${
                  activeTag
                    ? "border-[var(--theme-primary)] text-[var(--theme-text)]"
                    : ""
                }`}
              >
                <Tag size={14} />
                <span className="hidden sm:inline">
                  {t("personaPresets.tags", "标签")}
                </span>
                {activeTag && (
                  <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-[var(--theme-primary-light)] px-1 text-[11px]">
                    1
                  </span>
                )}
                <ChevronDown
                  size={14}
                  className={`transition-transform ${
                    isFilterOpen ? "rotate-180" : ""
                  }`}
                />
              </button>
              {isFilterOpen && (
                <div className="skill-filter-dropdown absolute right-0 top-[calc(100%+0.5rem)] z-20 w-72 rounded-2xl border p-3 shadow-lg">
                  <div className="mb-2 flex items-center justify-between">
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--theme-text-secondary)]">
                      {t("personaPresets.tags", "标签")}
                    </p>
                    {hasActiveFilters && (
                      <button
                        type="button"
                        onClick={clearFilters}
                        className="text-xs text-[var(--theme-text-secondary)] transition-colors hover:text-[var(--theme-primary)]"
                      >
                        {t("personaPresets.clearFilters", "清除筛选")}
                      </button>
                    )}
                  </div>
                  <div className="flex max-h-56 flex-wrap gap-2 overflow-y-auto">
                    {allTags.map((tag) => (
                      <button
                        key={tag}
                        type="button"
                        onClick={() => toggleTag(tag)}
                        className={`skill-tag-chip ${
                          activeTag === tag ? "skill-tag-chip--active" : ""
                        }`}
                      >
                        {tag}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : null
        }
        actions={
          canWrite ? (
            <button onClick={() => openModal(null)} className="btn-primary">
              <Plus size={16} />
              <span className="hidden sm:inline">
                {t("personaPresets.createMine", "新建角色")}
              </span>
            </button>
          ) : undefined
        }
      />

      <div className="skill-content-area flex-1 overflow-y-auto p-4 sm:p-6">
        {/* Scope tabs */}
        <div
          className="mb-5 flex items-center gap-1 rounded-xl p-1"
          style={{ background: "var(--skill-surface-alt)" }}
        >
          {scopeTabs.map(({ key, label, icon: Icon, count }) => (
            <button
              key={key}
              type="button"
              onClick={() => setScopeFilter(key)}
              className="flex flex-1 items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-all"
              style={{
                background:
                  scopeFilter === key ? "var(--skill-surface)" : "transparent",
                color:
                  scopeFilter === key
                    ? "var(--theme-text)"
                    : "var(--theme-text-secondary)",
                boxShadow: scopeFilter === key ? "var(--skill-shadow)" : "none",
              }}
            >
              <Icon size={15} />
              <span className="hidden sm:inline">{label}</span>
              <span
                className="text-xs"
                style={{ color: "var(--theme-text-secondary)" }}
              >
                {count}
              </span>
            </button>
          ))}
        </div>

        {filtered.length === 0 ? (
          <div className="skill-empty-state">
            <div className="skill-empty-state__icon">
              <UserRound size={28} />
            </div>
            <p className="skill-empty-state__title">
              {query || activeTag
                ? t("personaPresets.noMatch", "没有匹配的角色")
                : t("personaPresets.empty", "暂无角色预设")}
            </p>
            <p className="skill-empty-state__description">
              {query || activeTag
                ? t("personaPresets.tryOtherFilters", "试试其他搜索条件")
                : t("personaPresets.emptyHint", "管理员可以创建官方角色预设")}
            </p>
            {hasActiveFilters && (
              <button onClick={clearFilters} className="btn-secondary mt-4">
                {t("personaPresets.clearFilters", "清除筛选")}
              </button>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {filtered.map((preset, index) => {
              const selected = selectedPresetId === preset.id;
              const gradient = nameToGradient(preset.name);
              const primaryTag = preset.tags[0];
              return (
                <div
                  key={preset.id}
                  className="persona-card group flex h-full flex-col overflow-hidden rounded-2xl bg-[var(--theme-bg-card)] shadow-sm dark:shadow-none dark:border dark:border-[var(--theme-border)]"
                  style={{ animationDelay: `${index * 60}ms` }}
                >
                  {/* Gradient Banner */}
                  <div
                    className="persona-card__banner relative h-12 shrink-0"
                    style={{
                      background: `linear-gradient(45deg, ${gradient[0]}, ${gradient[1]}, ${gradient[2]})`,
                    }}
                  >
                    {selected && (
                      <div className="absolute top-2 right-2">
                        <span className="persona-card__status-pill persona-card__status-pill--selected">
                          {t("personaPresets.using", "使用中")}
                        </span>
                      </div>
                    )}
                  </div>

                  {/* Card Body */}
                  <div className="flex flex-1 flex-col p-4 pt-5">
                    <div className="flex items-start gap-3">
                      <div className="persona-card__avatar-ring shrink-0">
                        <span className="text-sm font-bold text-[var(--theme-primary)]">
                          {preset.name.charAt(0).toUpperCase()}
                        </span>
                      </div>
                      <div className="min-w-0 flex-1">
                        <h3
                          className="truncate text-base font-semibold text-[var(--theme-text)] leading-tight"
                          title={preset.name}
                        >
                          {preset.name}
                        </h3>
                        <div className="mt-1.5 flex items-center gap-2 text-[11px] text-[var(--theme-text-secondary)]">
                          <span>
                            {preset.scope === "global"
                              ? t("personaPresets.official", "官方")
                              : t("personaPresets.mine", "我的")}
                          </span>
                          {preset.usage_count > 0 && (
                            <>
                              <span className="inline-block h-1 w-1 rounded-full bg-[var(--theme-border)]" />
                              <span>
                                {preset.usage_count}
                                {t("personaPresets.usageCount", "次使用")}
                              </span>
                            </>
                          )}
                        </div>
                      </div>
                    </div>

                    <p className="mt-3 text-[13px] leading-relaxed text-[var(--theme-text-secondary)] line-clamp-2">
                      {preset.description || preset.system_prompt}
                    </p>

                    <div className="mt-3 flex flex-wrap items-center gap-1.5">
                      {primaryTag && (
                        <div className="flex items-center gap-1.5">
                          <Sparkles
                            size={12}
                            className="text-[var(--theme-text-secondary)]"
                          />
                          <span className="persona-card__scope-tag">
                            {primaryTag}
                          </span>
                        </div>
                      )}
                      {preset.tags.slice(1, 4).map((tag) => (
                        <button
                          key={tag}
                          type="button"
                          onClick={() => toggleTag(tag)}
                          className="persona-card__mini-tag"
                        >
                          {tag}
                        </button>
                      ))}
                      {preset.tags.length > 4 && (
                        <span className="persona-card__mini-tag">
                          +{preset.tags.length - 4}
                        </span>
                      )}
                    </div>

                    <div className="flex-1" />

                    <div className="mt-4 flex items-center justify-between gap-2 border-t border-[var(--theme-border)] pt-3">
                      <div className="flex items-center gap-2 text-[11px] text-[var(--theme-text-secondary)]">
                        <span className="inline-flex items-center gap-1">
                          <Tag size={11} />
                          {preset.tags.length}
                        </span>
                        {preset.skill_names.length > 0 && (
                          <>
                            <span className="inline-block h-1 w-1 rounded-full bg-[var(--theme-border)]" />
                            <span className="inline-flex items-center gap-1">
                              <Sparkles size={11} />
                              {preset.skill_names.length} skills
                            </span>
                          </>
                        )}
                      </div>
                      <div className="flex items-center gap-1.5">
                        {selected ? (
                          <button
                            onClick={handleClear}
                            className="persona-card__action-btn persona-card__action-btn--active"
                            title={t("personaPresets.clear", "清除使用")}
                          >
                            <Check size={16} />
                          </button>
                        ) : (
                          <button
                            onClick={() => handleUse(preset)}
                            className="persona-card__action-btn persona-card__action-btn--primary"
                            title={t("personaPresets.use", "使用")}
                          >
                            <Sparkles size={16} />
                          </button>
                        )}
                        {preset.scope === "global" && canWrite && (
                          <button
                            onClick={() => handleCopy(preset)}
                            className="persona-card__action-btn"
                            title={t("personaPresets.copy", "复制到我的角色")}
                          >
                            <Copy size={16} />
                          </button>
                        )}
                        {preset.scope === "user" && canWrite && (
                          <button
                            onClick={() => openModal(preset)}
                            className="persona-card__action-btn"
                            title={t("personaPresets.edit", "编辑")}
                          >
                            <Pencil size={16} />
                          </button>
                        )}
                        {preset.scope === "user" && canWrite && (
                          <button
                            onClick={() => setDeleteTarget(preset)}
                            className="persona-card__action-btn persona-card__action-btn--danger"
                            title={t("common.delete", "删除")}
                          >
                            <Trash2 size={16} />
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Create/Edit modal */}
      {showModal && canWrite && (
        <>
          <div
            className="fixed inset-0 z-[299] bg-black/50 sm:bg-transparent"
            onClick={closeModal}
          />
          <div
            className="modal-bottom-sheet sm:modal-centered-wrapper"
            onClick={closeModal}
          >
            <div
              ref={modalRef as React.Ref<HTMLDivElement>}
              className="modal-bottom-sheet-content sm:modal-centered-content sm:max-w-2xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="bottom-sheet-handle sm:hidden" />
              <div className="flex items-center justify-between glass-divider px-6 py-4">
                <div>
                  <h3 className="text-lg font-semibold text-stone-900 dark:text-stone-100">
                    {editingPreset
                      ? t("personaPresets.editMine", "编辑我的角色")
                      : t("personaPresets.createMine", "新建我的角色")}
                  </h3>
                  <p className="mt-0.5 text-xs text-[var(--theme-text-secondary)]">
                    {editingPreset
                      ? t(
                          "personaPresets.editHint",
                          "修改角色的名称、提示词和标签",
                        )
                      : t(
                          "personaPresets.createHint",
                          "定义角色的行为、语气和能力边界",
                        )}
                  </p>
                </div>
                <button onClick={closeModal} className="btn-icon">
                  <X size={20} />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-4 space-y-4">
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-stone-700 dark:text-stone-300">
                    {t("personaPresets.name", "名称")}{" "}
                    <span className="text-red-500">*</span>
                  </label>
                  <input
                    value={draft.name}
                    onChange={(e) =>
                      setDraft((prev) => ({ ...prev, name: e.target.value }))
                    }
                    className="glass-input h-10 w-full px-3 text-sm"
                    style={{ color: "var(--theme-text)" }}
                    placeholder={t(
                      "personaPresets.namePlaceholder",
                      "给角色起个名字",
                    )}
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-stone-700 dark:text-stone-300">
                    {t("personaPresets.description", "简介")}
                  </label>
                  <input
                    value={draft.description}
                    onChange={(e) =>
                      setDraft((prev) => ({
                        ...prev,
                        description: e.target.value,
                      }))
                    }
                    className="glass-input h-10 w-full px-3 text-sm"
                    style={{ color: "var(--theme-text)" }}
                    placeholder={t(
                      "personaPresets.descriptionPlaceholder",
                      "简短描述角色的能力和特点",
                    )}
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-stone-700 dark:text-stone-300">
                    {t("personaPresets.systemPrompt", "系统提示词")}{" "}
                    <span className="text-red-500">*</span>
                  </label>
                  <textarea
                    value={draft.system_prompt}
                    onChange={(e) =>
                      setDraft((prev) => ({
                        ...prev,
                        system_prompt: e.target.value,
                      }))
                    }
                    rows={10}
                    className="glass-input w-full resize-none px-4 py-3 text-sm leading-6"
                    style={{ color: "var(--theme-text)" }}
                    placeholder={t(
                      "personaPresets.systemPromptPlaceholder",
                      "定义角色的行为、语气和能力边界...",
                    )}
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-stone-700 dark:text-stone-300">
                    {t("personaPresets.tagsInput", "标签")}
                  </label>
                  <input
                    value={draft.tags}
                    onChange={(e) =>
                      setDraft((prev) => ({ ...prev, tags: e.target.value }))
                    }
                    className="glass-input h-10 w-full px-3 text-sm"
                    style={{ color: "var(--theme-text)" }}
                    placeholder={t(
                      "personaPresets.tagsInputPlaceholder",
                      "用逗号分隔，如：写作, 翻译, 代码",
                    )}
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-stone-700 dark:text-stone-300">
                    {t("personaPresets.skillsInput", "Skills")}
                  </label>
                  <input
                    value={draft.skill_names}
                    onChange={(e) =>
                      setDraft((prev) => ({
                        ...prev,
                        skill_names: e.target.value,
                      }))
                    }
                    className="glass-input h-10 w-full px-3 text-sm"
                    style={{ color: "var(--theme-text)" }}
                    placeholder={t(
                      "personaPresets.skillsInputPlaceholder",
                      "用逗号分隔，如：web_search, code_interpreter",
                    )}
                  />
                </div>
              </div>
              <div className="flex justify-end gap-2 px-6 py-4 glass-divider">
                <button onClick={closeModal} className="btn-secondary">
                  {t("common.cancel", "取消")}
                </button>
                <button
                  onClick={handleSave}
                  disabled={isMutating || !isFormValid}
                  className="btn-primary disabled:opacity-50"
                >
                  {isMutating ? (
                    <LoadingSpinner size="sm" />
                  ) : (
                    <Save size={16} />
                  )}
                  {t("common.save", "保存")}
                </button>
              </div>
            </div>
          </div>
        </>
      )}

      <ConfirmDialog
        isOpen={!!deleteTarget}
        title={t("personaPresets.confirmDelete", "删除角色")}
        message={
          deleteTarget
            ? t(
                "personaPresets.confirmDeleteMessage",
                "确定要删除角色「{name}」吗？此操作不可撤销。",
                { name: deleteTarget.name },
              )
            : ""
        }
        confirmText={t("common.delete", "删除")}
        cancelText={t("common.cancel", "取消")}
        variant="danger"
        loading={isDeleting}
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}

export default PersonaPlazaPanel;
