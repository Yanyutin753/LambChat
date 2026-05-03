import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
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
  Search,
  Camera,
  Loader2,
  GraduationCap,
  Code2,
  PenTool,
  Shield,
  Database,
  Zap,
  Package,
  type LucideIcon,
} from "lucide-react";
import { PanelHeader } from "../common/PanelHeader";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { LoadingSpinner } from "../common/LoadingSpinner";
import toast from "react-hot-toast";
import { PersonaPlazaSkeleton } from "../skeletons";
import { useAuth } from "../../hooks/useAuth";
import { usePersonaPresets } from "../../hooks/usePersonaPresets";
import { useSkills } from "../../hooks/useSkills";
import { useSwipeToClose } from "../../hooks/useSwipeToClose";
import { buildPersonaPresetPayload } from "./personaPresetEditor";
import { getPersonaPresetCapabilities } from "./personaPresetAccess";
import {
  getCategoryIcon,
  nameToGradient,
} from "../panels/MarketplacePanel/constants";
import type { PersonaPreset, PersonaPresetStatus } from "../../types";
import { Permission } from "../../types";
import { uploadApi } from "../../services/api";
import { compressImageFile } from "../../utils/imageCompression";
import { renderToStaticMarkup } from "react-dom/server";

const SESSION_CONFIG_KEY = "lambchat_session_config";

const AVATAR_ICONS: {
  icon: LucideIcon;
  label: string;
  color: string;
  bg: string;
}[] = [
  { icon: Sparkles, label: "Sparkles", color: "#6366f1", bg: "#eef2ff" },
  { icon: GraduationCap, label: "Academic", color: "#0891b2", bg: "#ecfeff" },
  { icon: Code2, label: "Coding", color: "#16a34a", bg: "#f0fdf4" },
  { icon: PenTool, label: "Writing", color: "#c026d3", bg: "#fdf4ff" },
  { icon: Shield, label: "Security", color: "#dc2626", bg: "#fef2f2" },
  { icon: Database, label: "Data", color: "#ea580c", bg: "#fff7ed" },
  { icon: Zap, label: "Productivity", color: "#ca8a04", bg: "#fefce8" },
  { icon: Package, label: "General", color: "#4f46e5", bg: "#eef2ff" },
];

function iconToSvgDataUrl(item: (typeof AVATAR_ICONS)[number]): string {
  const raw = renderToStaticMarkup(<item.icon size={48} color={item.color} />);
  const inner = raw.replace(/^<svg[^>]*>/, "").replace(/<\/svg>$/, "");
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80"><circle cx="40" cy="40" r="40" fill="${item.bg}"/><g transform="translate(16,16)">${inner}</g></svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

function readPersonaPresetId(): string | null {
  try {
    const raw = localStorage.getItem(SESSION_CONFIG_KEY);
    if (!raw) return null;
    return JSON.parse(raw)?.personaPresetId || null;
  } catch {
    return null;
  }
}

type ScopeFilter = "all" | "global" | "user";

export function PersonaPlazaPanel() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { hasPermission } = useAuth();
  const canRead = hasPermission(Permission.PERSONA_PRESET_READ);
  const canWrite = hasPermission(Permission.PERSONA_PRESET_WRITE);
  const canAdmin = hasPermission(Permission.PERSONA_PRESET_ADMIN);

  const {
    presets,
    isLoading,
    isMutating,
    usePreset: activatePreset,
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
  const [editorScope, setEditorScope] = useState<"user" | "global">("user");
  const [editorStatus, setEditorStatus] =
    useState<PersonaPresetStatus>("draft");
  const [draft, setDraft] = useState({
    name: "",
    description: "",
    avatar: "",
    system_prompt: "",
    tags: "",
    skill_names: [] as string[],
  });

  const [deleteTarget, setDeleteTarget] = useState<PersonaPreset | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isScopeOpen, setIsScopeOpen] = useState(false);
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [skillDropdownOpen, setSkillDropdownOpen] = useState(false);
  const [skillSearch, setSkillSearch] = useState("");
  const skillDropdownRef = useRef<HTMLDivElement>(null);
  const scopeBtnRef = useRef<HTMLButtonElement>(null);
  const tagBtnRef = useRef<HTMLButtonElement>(null);
  const avatarInputRef = useRef<HTMLInputElement>(null);
  const [isUploadingAvatar, setIsUploadingAvatar] = useState(false);

  const { skills: allSkills } = useSkills({ enabled: showModal });

  const availableSkills = useMemo(() => {
    const q = skillSearch.trim().toLowerCase();
    return allSkills.filter(
      (s) =>
        !draft.skill_names.includes(s.name) &&
        (!q ||
          s.name.toLowerCase().includes(q) ||
          (s.description || "").toLowerCase().includes(q)),
    );
  }, [allSkills, draft.skill_names, skillSearch]);

  const closeModal = useCallback(() => {
    setShowModal(false);
    setEditingPreset(null);
    setEditorScope("user");
    setEditorStatus("draft");
    setSkillDropdownOpen(false);
    setSkillSearch("");
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
      if (isScopeOpen && !target.closest("[data-scope-filter]")) {
        setIsScopeOpen(false);
      }
      if (
        skillDropdownOpen &&
        skillDropdownRef.current &&
        !skillDropdownRef.current.contains(target)
      ) {
        setSkillDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [isFilterOpen, isScopeOpen, skillDropdownOpen]);

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
      const snapshot = await activatePreset(preset.id);
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
        } catch {
          // Ignore local session cache write failures.
        }
        navigate(`/chat?persona=${preset.id}`);
        toast.success(
          t("personaPresets.useSuccess", "已切换到角色「{{name}}」", {
            name: preset.name,
          }),
        );
      }
    },
    [activatePreset, navigate, t],
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
    } catch {
      // Ignore local session cache write failures.
    }
    toast.success(t("personaPresets.clearSuccess", "已清除当前角色"));
  }, [t]);

  const handleCopy = useCallback(
    async (preset: PersonaPreset) => {
      const ok = await copyPreset(preset.id);
      if (ok) {
        toast.success(
          t("personaPresets.copySuccess", "已复制角色「{{name}}」", {
            name: preset.name,
          }),
        );
      }
    },
    [copyPreset, t],
  );

  const openModal = (
    preset: PersonaPreset | null,
    scope: "user" | "global" = preset?.scope ?? "user",
  ) => {
    setEditingPreset(preset);
    setEditorScope(scope);
    setEditorStatus(
      preset?.status ?? (scope === "global" ? "published" : "draft"),
    );
    setDraft({
      name: preset?.name || "",
      description: preset?.description || "",
      avatar: preset?.avatar || "",
      system_prompt: preset?.system_prompt || "",
      tags: preset?.tags.join(", ") || "",
      skill_names: preset?.skill_names || [],
    });
    setShowModal(true);
  };

  const handleSave = useCallback(async () => {
    if (!draft.name.trim() || !draft.system_prompt.trim()) return;
    const normalizedDraft = {
      name: draft.name.trim(),
      description: draft.description.trim(),
      avatar: draft.avatar,
      system_prompt: draft.system_prompt.trim(),
      tags: draft.tags
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      skill_names: draft.skill_names,
    };

    const saved = editingPreset
      ? await updatePreset(
          editingPreset.id,
          buildPersonaPresetPayload(editingPreset, normalizedDraft, {
            scope: editorScope,
            status: editorStatus,
          }),
        )
      : await createPreset(
          buildPersonaPresetPayload(null, normalizedDraft, {
            scope: editorScope,
            status: editorStatus,
          }),
        );
    if (saved) {
      closeModal();
      toast.success(
        editingPreset
          ? t("personaPresets.updateSuccess", "角色「{{name}}」已更新", {
              name: normalizedDraft.name,
            })
          : t("personaPresets.createSuccess", "角色「{{name}}」已创建", {
              name: normalizedDraft.name,
            }),
      );
    }
  }, [
    closeModal,
    createPreset,
    draft,
    editingPreset,
    editorScope,
    editorStatus,
    t,
    updatePreset,
  ]);

  const handleAvatarUpload = useCallback(
    async (file: File) => {
      setIsUploadingAvatar(true);
      try {
        const compressed = await compressImageFile(file, {
          maxDimension: 256,
          targetSizeKB: 100,
          skipBelowKB: 100,
        });
        const result = await uploadApi.uploadFile(compressed, {
          folder: "persona-avatars",
        }).promise;
        setDraft((prev) => ({ ...prev, avatar: result.url }));
      } catch (error) {
        console.error("Avatar upload failed:", error);
        toast.error(t("personaPresets.avatarUploadFailed", "头像上传失败"));
      } finally {
        setIsUploadingAvatar(false);
      }
    },
    [t],
  );

  const handleDelete = useCallback(async () => {
    if (!deleteTarget) return;
    setIsDeleting(true);
    const ok = await deletePreset(deleteTarget.id);
    setIsDeleting(false);
    if (ok) {
      toast.success(
        t("personaPresets.deleteSuccess", "角色「{{name}}」已删除", {
          name: deleteTarget.name,
        }),
      );
      if (selectedPresetId === deleteTarget.id) handleClear();
    }
    setDeleteTarget(null);
  }, [deleteTarget, deletePreset, selectedPresetId, handleClear, t]);

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
          <div className="flex items-center gap-2">
            <div className="shrink-0" data-scope-filter>
              <button
                ref={scopeBtnRef}
                type="button"
                onClick={() => {
                  setIsScopeOpen((prev) => !prev);
                  setIsFilterOpen(false);
                }}
                className={`btn-secondary h-10 px-2.5 ${
                  scopeFilter !== "all"
                    ? "border-[var(--theme-primary)] text-[var(--theme-text)]"
                    : ""
                }`}
              >
                {(() => {
                  const current = scopeTabs.find((s) => s.key === scopeFilter)!;
                  const CurrentIcon = current.icon;
                  return (
                    <>
                      <CurrentIcon size={13} />
                      <span className="hidden sm:inline">{current.label}</span>
                    </>
                  );
                })()}
                <ChevronDown
                  size={13}
                  className={`transition-transform ${
                    isScopeOpen ? "rotate-180" : ""
                  }`}
                />
              </button>
            </div>
            {allTags.length > 0 && (
              <div className="shrink-0" data-persona-filter>
                <button
                  ref={tagBtnRef}
                  type="button"
                  onClick={() => {
                    setIsFilterOpen((prev) => !prev);
                    setIsScopeOpen(false);
                  }}
                  className={`btn-secondary h-10 px-2.5 ${
                    activeTag
                      ? "border-[var(--theme-primary)] text-[var(--theme-text)]"
                      : ""
                  }`}
                >
                  <Tag size={13} />
                  <span className="hidden sm:inline">
                    {t("personaPresets.tags", "标签")}
                  </span>
                  {activeTag && (
                    <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-[var(--theme-primary-light)] px-1 text-[10px]">
                      1
                    </span>
                  )}
                  <ChevronDown
                    size={13}
                    className={`transition-transform ${
                      isFilterOpen ? "rotate-180" : ""
                    }`}
                  />
                </button>
              </div>
            )}
          </div>
        }
        actions={
          canWrite || canAdmin ? (
            <div className="flex items-center gap-2">
              {canWrite && (
                <button
                  onClick={() => openModal(null, "user")}
                  className="btn-secondary h-10"
                >
                  <Plus size={16} />
                  <span className="hidden sm:inline">
                    {t("personaPresets.createMine", "新建我的角色")}
                  </span>
                </button>
              )}
              {canAdmin && (
                <button
                  onClick={() => openModal(null, "global")}
                  className="btn-primary h-10"
                >
                  <Sparkles size={16} />
                  <span className="hidden sm:inline">
                    {t("personaPresets.publishOfficial", "发布官方角色")}
                  </span>
                </button>
              )}
            </div>
          ) : undefined
        }
      />

      <div className="skill-content-area flex-1 overflow-y-auto p-4 sm:p-6">
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
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 sm:gap-5 lg:grid-cols-3">
            {filtered.map((preset, index) => {
              const selected = selectedPresetId === preset.id;
              const gradient = nameToGradient(preset.name);
              const primaryTag = preset.tags[0];
              const CategoryIcon = primaryTag
                ? getCategoryIcon(primaryTag)
                : Sparkles;
              const capabilities = getPersonaPresetCapabilities(preset, {
                canWrite,
                canAdmin,
              });
              return (
                <div
                  key={preset.id}
                  className="mp-card group flex h-full flex-col overflow-hidden rounded-2xl bg-[var(--theme-bg-card)] shadow-sm dark:shadow-none dark:border dark:border-[var(--theme-border)]"
                  style={{ animationDelay: `${index * 60}ms` }}
                >
                  {/* Gradient Banner */}
                  <div
                    className="mp-card__banner relative h-12 shrink-0"
                    style={{
                      background: `linear-gradient(45deg, ${gradient[0]}, ${gradient[1]}, ${gradient[2]})`,
                    }}
                  >
                    <div className="absolute top-2 right-2 flex gap-1.5">
                      {selected && (
                        <span className="mp-card__status-pill mp-card__status-pill--installed">
                          {t("personaPresets.using", "使用中")}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Card Body */}
                  <div className="flex flex-1 flex-col p-4 pt-5">
                    {/* Title row with avatar or icon */}
                    <div className="flex items-start gap-3">
                      {preset.avatar ? (
                        <div className="mp-card__avatar-ring shrink-0">
                          <img
                            src={preset.avatar}
                            alt=""
                            className="mp-card__avatar-img"
                            onError={(e) => {
                              (e.target as HTMLImageElement).style.display =
                                "none";
                            }}
                          />
                          <CategoryIcon
                            size={20}
                            className="text-[var(--theme-primary)]"
                          />
                        </div>
                      ) : (
                        <div className="mp-card__icon-ring shrink-0">
                          <CategoryIcon
                            size={20}
                            className="text-[var(--theme-primary)]"
                          />
                        </div>
                      )}
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
                          {preset.scope === "global" && (
                            <>
                              <span className="inline-block h-1 w-1 rounded-full bg-[var(--theme-border)]" />
                              <span>
                                {preset.status === "published"
                                  ? t("personaPresets.published", "已发布")
                                  : preset.status === "archived"
                                    ? t("personaPresets.archived", "已归档")
                                    : t("personaPresets.draft", "草稿")}
                              </span>
                            </>
                          )}
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

                    {/* Description */}
                    <p className="mt-3 text-[13px] leading-relaxed text-[var(--theme-text-secondary)] line-clamp-2">
                      {preset.description || preset.system_prompt}
                    </p>

                    {/* Category tag + mini tags */}
                    {primaryTag && (
                      <div className="mt-3 flex items-center gap-1.5">
                        <CategoryIcon
                          size={12}
                          className="text-[var(--theme-text-secondary)]"
                        />
                        <span className="mp-card__category-tag">
                          {primaryTag}
                        </span>
                      </div>
                    )}

                    {preset.tags.length > 1 && (
                      <div className="mt-3 flex flex-wrap gap-1.5">
                        {preset.tags.slice(1, 4).map((tag) => (
                          <button
                            key={tag}
                            type="button"
                            onClick={() => toggleTag(tag)}
                            className={`mp-card__mini-tag ${
                              activeTag === tag
                                ? "mp-card__mini-tag--active"
                                : ""
                            }`}
                          >
                            {tag}
                          </button>
                        ))}
                        {preset.tags.length > 4 && (
                          <span className="mp-card__mini-tag">
                            +{preset.tags.length - 4}
                          </span>
                        )}
                      </div>
                    )}

                    {/* Spacer */}
                    <div className="flex-1" />

                    {/* Meta & Actions */}
                    <div className="mt-4 flex items-center justify-between gap-2 border-t border-[var(--theme-border)] pt-3">
                      <div className="flex items-center gap-2 text-[11px] text-[var(--theme-text-secondary)]">
                        {preset.skill_names.length > 0 && (
                          <span className="inline-flex items-center gap-1">
                            <Sparkles size={11} />
                            {preset.skill_names.length} skills
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-1.5">
                        {selected ? (
                          <button
                            onClick={handleClear}
                            className="mp-card__action-btn mp-card__action-btn--ghost"
                            title={t("personaPresets.clear", "清除使用")}
                          >
                            <Check size={16} />
                          </button>
                        ) : (
                          <button
                            onClick={() => handleUse(preset)}
                            className="mp-card__action-btn mp-card__action-btn--ghost"
                            title={t("personaPresets.use", "使用")}
                          >
                            <Sparkles size={16} />
                          </button>
                        )}
                        {capabilities.canCopy && (
                          <button
                            onClick={() => handleCopy(preset)}
                            className="mp-card__action-btn mp-card__action-btn--ghost"
                            title={t("personaPresets.copy", "复制到我的角色")}
                          >
                            <Copy size={16} />
                          </button>
                        )}
                        {capabilities.canEdit && (
                          <button
                            onClick={() => openModal(preset)}
                            className="mp-card__action-btn mp-card__action-btn--ghost"
                            title={t("personaPresets.edit", "编辑")}
                          >
                            <Pencil size={16} />
                          </button>
                        )}
                        {capabilities.canDelete && (
                          <button
                            onClick={() => setDeleteTarget(preset)}
                            className="mp-card__action-btn"
                            title={t("common.delete", "删除")}
                            style={{ color: "#dc2626" }}
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
      {showModal && (canWrite || canAdmin) && (
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

              {/* Header */}
              <div className="ppe-modal-header flex items-center justify-between border-b border-[var(--theme-border)] px-5 py-4 sm:px-6 sm:py-5">
                <div className="flex items-center gap-3 sm:gap-3.5">
                  <div className="ppe-header-icon">
                    {editingPreset ? <Pencil size={18} /> : <Plus size={18} />}
                  </div>
                  <div className="min-w-0">
                    <h3 className="truncate text-sm font-semibold sm:text-base text-[var(--theme-text)]">
                      {editingPreset
                        ? editingPreset.scope === "global"
                          ? t("personaPresets.editOfficial", "编辑官方角色")
                          : t("personaPresets.editMine", "编辑我的角色")
                        : editorScope === "global"
                          ? t("personaPresets.publishOfficial", "发布官方角色")
                          : t("personaPresets.createMine", "新建我的角色")}
                    </h3>
                    <p className="mt-0.5 text-xs text-[var(--theme-text-secondary)] line-clamp-1 sm:line-clamp-none">
                      {editorScope === "global"
                        ? t(
                            "personaPresets.officialHint",
                            "官方角色会展示给所有用户，建议补全简介、标签和可用技能。",
                          )
                        : t(
                            "personaPresets.createHint",
                            "定义角色的行为、语气和能力边界",
                          )}
                    </p>
                  </div>
                </div>
                <button
                  onClick={closeModal}
                  className="flex size-8 shrink-0 items-center justify-center rounded-lg text-[var(--theme-text-secondary)] transition-colors hover:bg-[var(--theme-primary-light)] active:opacity-70"
                >
                  <X size={18} />
                </button>
              </div>

              {/* Form Body */}
              <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-4 sm:py-5 space-y-4 sm:space-y-5">
                {/* Admin: Scope & Status */}
                {canAdmin && (
                  <div
                    className="ppe-section ppe-field-animated"
                    style={{ animationDelay: "0ms" }}
                  >
                    <div className="grid gap-4 sm:grid-cols-2">
                      <div className="ppe-field">
                        <label className="ppe-label">
                          {t("personaPresets.scope", "范围")}
                        </label>
                        <select
                          value={editorScope}
                          onChange={(event) =>
                            setEditorScope(
                              event.target.value as "user" | "global",
                            )
                          }
                          disabled={!!editingPreset}
                          className="ppe-select"
                        >
                          <option value="user">
                            {t("personaPresets.mine", "我的")}
                          </option>
                          <option value="global">
                            {t("personaPresets.official", "官方")}
                          </option>
                        </select>
                      </div>
                      {editorScope === "global" && (
                        <div className="ppe-field">
                          <label className="ppe-label">
                            {t("personaPresets.status", "状态")}
                          </label>
                          <select
                            value={editorStatus}
                            onChange={(event) =>
                              setEditorStatus(
                                event.target.value as PersonaPresetStatus,
                              )
                            }
                            className="ppe-select"
                          >
                            <option value="draft">
                              {t("personaPresets.draft", "草稿")}
                            </option>
                            <option value="published">
                              {t("personaPresets.published", "已发布")}
                            </option>
                            <option value="archived">
                              {t("personaPresets.archived", "已归档")}
                            </option>
                          </select>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Avatar */}
                <div
                  className="ppe-field ppe-field-animated"
                  style={{ animationDelay: "40ms" }}
                >
                  <label className="ppe-label">
                    {t("personaPresets.avatar", "头像")}
                  </label>
                  <div className="ppe-avatar-upload">
                    <div className="ppe-avatar-preview">
                      {draft.avatar ? (
                        <>
                          <img
                            src={draft.avatar}
                            alt=""
                            className="ppe-avatar-img"
                            onError={() =>
                              setDraft((prev) => ({ ...prev, avatar: "" }))
                            }
                          />
                          <button
                            type="button"
                            className="ppe-avatar-remove"
                            onClick={() =>
                              setDraft((prev) => ({ ...prev, avatar: "" }))
                            }
                            title={t("common.remove", "移除")}
                          >
                            <X size={14} />
                          </button>
                        </>
                      ) : (
                        <div
                          className="ppe-avatar-placeholder"
                          onClick={() => avatarInputRef.current?.click()}
                        >
                          <Camera size={22} />
                          <span className="ppe-avatar-placeholder-text">
                            {t("personaPresets.uploadAvatar", "上传头像")}
                          </span>
                        </div>
                      )}
                      {isUploadingAvatar && (
                        <div className="ppe-avatar-uploading">
                          <Loader2 size={20} className="animate-spin" />
                        </div>
                      )}
                    </div>
                    {!draft.avatar && (
                      <div className="mt-3 grid grid-cols-4 gap-2">
                        {AVATAR_ICONS.map((item) => {
                          const Icon = item.icon;
                          return (
                            <button
                              key={item.label}
                              type="button"
                              className="ppe-icon-option"
                              style={
                                {
                                  "--icon-color": item.color,
                                  "--icon-bg": item.bg,
                                } as React.CSSProperties
                              }
                              onClick={() =>
                                setDraft((prev) => ({
                                  ...prev,
                                  avatar: iconToSvgDataUrl(item),
                                }))
                              }
                              title={item.label}
                            >
                              <Icon size={18} style={{ color: item.color }} />
                            </button>
                          );
                        })}
                      </div>
                    )}
                    <input
                      ref={avatarInputRef}
                      type="file"
                      accept="image/*"
                      className="hidden"
                      disabled={isUploadingAvatar}
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) handleAvatarUpload(file);
                        e.target.value = "";
                      }}
                    />
                    {draft.avatar && (
                      <button
                        type="button"
                        className="ppe-avatar-hint-btn"
                        disabled={isUploadingAvatar}
                        onClick={() => avatarInputRef.current?.click()}
                      >
                        <Camera size={12} />
                        {t("personaPresets.changeAvatar", "更换头像")}
                      </button>
                    )}
                  </div>
                </div>

                {/* Name */}
                <div
                  className="ppe-field ppe-field-animated"
                  style={{ animationDelay: "80ms" }}
                >
                  <label className="ppe-label">
                    {t("personaPresets.name", "名称")}
                    <span className="ml-0.5 text-red-500">*</span>
                  </label>
                  <input
                    value={draft.name}
                    onChange={(e) =>
                      setDraft((prev) => ({ ...prev, name: e.target.value }))
                    }
                    className="ppe-input"
                    placeholder={t(
                      "personaPresets.namePlaceholder",
                      "给角色起个名字",
                    )}
                  />
                </div>

                {/* Description */}
                <div
                  className="ppe-field ppe-field-animated"
                  style={{ animationDelay: "120ms" }}
                >
                  <label className="ppe-label">
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
                    className="ppe-input"
                    placeholder={t(
                      "personaPresets.descriptionPlaceholder",
                      "简短描述角色的能力和特点",
                    )}
                  />
                </div>

                {/* System Prompt */}
                <div
                  className="ppe-field ppe-field-animated"
                  style={{ animationDelay: "160ms" }}
                >
                  <label className="ppe-label">
                    {t("personaPresets.systemPrompt", "系统提示词")}
                    <span className="ml-0.5 text-red-500">*</span>
                  </label>
                  <textarea
                    value={draft.system_prompt}
                    onChange={(e) =>
                      setDraft((prev) => ({
                        ...prev,
                        system_prompt: e.target.value,
                      }))
                    }
                    rows={8}
                    className="ppe-textarea"
                    placeholder={t(
                      "personaPresets.systemPromptPlaceholder",
                      "定义角色的行为、语气和能力边界...",
                    )}
                  />
                  <div className="ppe-char-counter">
                    {draft.system_prompt.length}
                  </div>
                </div>

                {/* Tags */}
                <div
                  className="ppe-field ppe-field-animated"
                  style={{ animationDelay: "200ms" }}
                >
                  <label className="ppe-label">
                    {t("personaPresets.tagsInput", "标签")}
                  </label>
                  <input
                    value={draft.tags}
                    onChange={(e) =>
                      setDraft((prev) => ({ ...prev, tags: e.target.value }))
                    }
                    className="ppe-input"
                    placeholder={t(
                      "personaPresets.tagsInputPlaceholder",
                      "用逗号分隔，如：写作, 翻译, 代码",
                    )}
                  />
                  {draft.tags.trim() && (
                    <div className="mt-2.5 flex flex-wrap gap-1.5">
                      {draft.tags
                        .split(",")
                        .map((s) => s.trim())
                        .filter(Boolean)
                        .map((tag, idx) => (
                          <span
                            key={tag}
                            className="ppe-tag-chip"
                            style={{ animationDelay: `${idx * 30}ms` }}
                          >
                            <Tag size={10} />
                            {tag}
                          </span>
                        ))}
                    </div>
                  )}
                </div>

                {/* Skills Selector */}
                <div
                  className="ppe-field ppe-field-animated"
                  style={{ animationDelay: "240ms" }}
                >
                  <label className="ppe-label">
                    <span className="flex items-center gap-1.5">
                      <Sparkles
                        size={13}
                        className="text-[var(--theme-primary)]"
                      />
                      {t("personaPresets.skillsInput", "Skills")}
                    </span>
                  </label>
                  <div ref={skillDropdownRef} className="relative">
                    <button
                      type="button"
                      onClick={() => {
                        setSkillDropdownOpen((v) => !v);
                        setSkillSearch("");
                      }}
                      className="ppe-skill-trigger"
                    >
                      {draft.skill_names.length > 0 ? (
                        <div className="flex flex-wrap gap-1.5">
                          {draft.skill_names.map((name) => (
                            <span key={name} className="ppe-skill-chip">
                              {name}
                              <X
                                size={12}
                                className="ppe-skill-chip-remove"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setDraft((prev) => ({
                                    ...prev,
                                    skill_names: prev.skill_names.filter(
                                      (n) => n !== name,
                                    ),
                                  }));
                                }}
                              />
                            </span>
                          ))}
                        </div>
                      ) : (
                        <span className="text-[var(--theme-text-secondary)]">
                          {t(
                            "personaPresets.skillsInputPlaceholder",
                            "点击选择可用技能...",
                          )}
                        </span>
                      )}
                      <ChevronDown
                        size={14}
                        className={`shrink-0 text-[var(--theme-text-secondary)] transition-transform duration-200 ${
                          skillDropdownOpen ? "rotate-180" : ""
                        }`}
                      />
                    </button>

                    {skillDropdownOpen && (
                      <div className="ppe-skill-dropdown">
                        <div className="p-2.5 border-b border-[var(--theme-border)]">
                          <div className="relative">
                            <Search
                              size={14}
                              className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--theme-text-secondary)]"
                            />
                            <input
                              type="text"
                              value={skillSearch}
                              onChange={(e) => setSkillSearch(e.target.value)}
                              placeholder={t(
                                "skills.searchPlaceholder",
                                "搜索技能...",
                              )}
                              className="ppe-skill-search"
                              autoFocus
                            />
                          </div>
                        </div>
                        <div className="max-h-48 overflow-y-auto p-1.5">
                          {availableSkills.length > 0 ? (
                            availableSkills.map((skill) => (
                              <button
                                key={skill.name}
                                type="button"
                                onClick={() => {
                                  setDraft((prev) => ({
                                    ...prev,
                                    skill_names: [
                                      ...prev.skill_names,
                                      skill.name,
                                    ],
                                  }));
                                  setSkillSearch("");
                                }}
                                className="ppe-skill-option"
                              >
                                <div className="flex-1 min-w-0">
                                  <div className="text-sm font-medium text-[var(--theme-text)] truncate">
                                    {skill.name}
                                  </div>
                                  {skill.description && (
                                    <div className="text-[11px] text-[var(--theme-text-secondary)] truncate mt-0.5">
                                      {skill.description}
                                    </div>
                                  )}
                                </div>
                                <Plus
                                  size={14}
                                  className="shrink-0 text-[var(--theme-text-secondary)]"
                                />
                              </button>
                            ))
                          ) : (
                            <div className="px-3 py-6 text-center text-xs text-[var(--theme-text-secondary)]">
                              {skillSearch.trim()
                                ? t("skills.noMatchingSkills", "没有匹配的技能")
                                : t(
                                    "personaPresets.allSkillsSelected",
                                    "所有技能已选择",
                                  )}
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Footer */}
              <div className="ppe-modal-footer flex justify-end gap-2.5 border-t border-[var(--theme-border)] px-4 py-3.5 pb-[max(0.875rem,env(safe-area-inset-bottom))] sm:px-6 sm:pb-4">
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
                "确定要删除角色「{{name}}」吗？此操作不可撤销。",
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

      {isScopeOpen &&
        scopeBtnRef.current &&
        createPortal(
          <div
            className="fixed inset-0 z-[999]"
            onMouseDown={() => setIsScopeOpen(false)}
          >
            <div
              className="absolute w-44 rounded-xl border bg-[var(--theme-bg-card,#1c1917)] p-1 shadow-lg"
              style={{
                top: scopeBtnRef.current.getBoundingClientRect().bottom + 8,
                left: scopeBtnRef.current.getBoundingClientRect().right - 176,
              }}
              onMouseDown={(e) => e.stopPropagation()}
            >
              {scopeTabs.map(({ key, label, icon: Icon, count }) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => {
                    setScopeFilter(key);
                    setIsScopeOpen(false);
                  }}
                  className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors"
                  style={{
                    background:
                      scopeFilter === key
                        ? "var(--skill-surface-alt)"
                        : "var(--theme-bg-card, #1c1917)",
                    color:
                      scopeFilter === key
                        ? "var(--theme-text)"
                        : "var(--theme-text-secondary)",
                  }}
                >
                  <Icon size={14} />
                  <span className="flex-1 text-left">{label}</span>
                  <span
                    className="text-xs"
                    style={{ color: "var(--theme-text-secondary)" }}
                  >
                    {count}
                  </span>
                </button>
              ))}
            </div>
          </div>,
          document.body,
        )}

      {isFilterOpen &&
        tagBtnRef.current &&
        createPortal(
          <div
            className="fixed inset-0 z-[999]"
            onMouseDown={() => setIsFilterOpen(false)}
          >
            <div
              className="skill-filter-dropdown absolute w-72 rounded-2xl border bg-[var(--skill-surface)] p-3 shadow-lg"
              style={{
                top: tagBtnRef.current.getBoundingClientRect().bottom + 8,
                right:
                  window.innerWidth -
                  tagBtnRef.current.getBoundingClientRect().right,
              }}
              onMouseDown={(e) => e.stopPropagation()}
            >
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
          </div>,
          document.body,
        )}
    </div>
  );
}

export default PersonaPlazaPanel;
