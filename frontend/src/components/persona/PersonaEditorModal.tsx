import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Plus,
  Pencil,
  X,
  Sparkles,
  Tag,
  ChevronDown,
  Save,
  Search,
  Camera,
  Loader2,
  Smile,
  MessageSquare,
  GraduationCap,
  Code2,
  PenTool,
  Shield,
  Database,
  Zap,
  Package,
  Check,
  type LucideIcon,
} from "lucide-react";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { EditorSidebar } from "../common/EditorSidebar";
import toast from "react-hot-toast";
import { useSkills } from "../../hooks/useSkills";
import { buildPersonaPresetPayload } from "./personaPresetEditor";
import { uploadApi } from "../../services/api";
import { compressImageFile } from "../../utils/imageCompression";
import {
  getPersonaAvatarIconValue,
  getPersonaAvatarIcons,
  isPersonaImageAvatar,
  type PersonaAvatarIconKey,
} from "./personaAvatar";
import { PersonaAvatarIcon, PersonaAvatarImage } from "./PersonaAvatarIcon";
import type {
  PersonaPreset,
  PersonaPresetCreate,
  PersonaPresetStatus,
  PersonaPresetUpdate,
} from "../../types";

const AVATAR_ICONS: {
  key: PersonaAvatarIconKey;
  icon: LucideIcon;
  label: string;
  color: string;
  bg: string;
}[] = getPersonaAvatarIcons().map((item) => ({
  ...item,
  icon:
    {
      sparkles: Sparkles,
      academic: GraduationCap,
      coding: Code2,
      writing: PenTool,
      security: Shield,
      data: Database,
      productivity: Zap,
      general: Package,
    }[item.key] ?? Sparkles,
}));

interface PersonaEditorModalProps {
  showModal: boolean;
  editingPreset: PersonaPreset | null;
  editorScope: "user" | "global";
  canAdmin: boolean;
  isMutating: boolean;
  createPreset: (data: PersonaPresetCreate) => Promise<PersonaPreset | null>;
  updatePreset: (
    presetId: string,
    data: PersonaPresetUpdate,
  ) => Promise<PersonaPreset | null>;
  onClose: () => void;
}

export function PersonaEditorModal({
  showModal,
  editingPreset,
  editorScope: initialScope,
  canAdmin,
  isMutating,
  createPreset,
  updatePreset,
  onClose,
}: PersonaEditorModalProps) {
  const { t } = useTranslation();
  const [editorScope, setEditorScope] = useState<"user" | "global">(
    initialScope,
  );
  const [editorStatus, setEditorStatus] = useState<PersonaPresetStatus>(
    editingPreset?.status ??
      (initialScope === "global" ? "published" : "draft"),
  );
  const [draft, setDraft] = useState({
    name: editingPreset?.name || "",
    description: editingPreset?.description || "",
    avatar: editingPreset?.avatar || "",
    system_prompt: editingPreset?.system_prompt || "",
    tags: editingPreset?.tags.join(", ") || "",
    skill_names: [...(editingPreset?.skill_names || [])] as string[],
  });

  useEffect(() => {
    if (showModal) {
      setEditorScope(initialScope);
      setEditorStatus(
        editingPreset?.status ??
          (initialScope === "global" ? "published" : "draft"),
      );
      setDraft({
        name: editingPreset?.name || "",
        description: editingPreset?.description || "",
        avatar: editingPreset?.avatar || "",
        system_prompt: editingPreset?.system_prompt || "",
        tags: editingPreset?.tags.join(", ") || "",
        skill_names: [...(editingPreset?.skill_names || [])] as string[],
      });
      setSkillSearch("");
      setSkillDropdownOpen(false);
      setIconPickerOpen(false);
    }
  }, [showModal, editingPreset, initialScope]);

  const [skillDropdownOpen, setSkillDropdownOpen] = useState(false);
  const [skillSearch, setSkillSearch] = useState("");
  const skillDropdownRef = useRef<HTMLDivElement>(null);
  const avatarInputRef = useRef<HTMLInputElement>(null);
  const iconPickerRef = useRef<HTMLDivElement>(null);
  const [iconPickerOpen, setIconPickerOpen] = useState(false);
  const [isUploadingAvatar, setIsUploadingAvatar] = useState(false);

  const { skills: allSkills } = useSkills({ enabled: showModal });

  const displayedSkills = useMemo(() => {
    const q = skillSearch.trim().toLowerCase();
    return allSkills
      .filter(
        (s) =>
          !q ||
          s.name.toLowerCase().includes(q) ||
          (s.description || "").toLowerCase().includes(q),
      )
      .sort((a, b) => {
        const aSel = draft.skill_names.includes(a.name) ? 0 : 1;
        const bSel = draft.skill_names.includes(b.name) ? 0 : 1;
        return aSel - bSel;
      });
  }, [allSkills, draft.skill_names, skillSearch]);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (
        skillDropdownOpen &&
        skillDropdownRef.current &&
        !skillDropdownRef.current.contains(target)
      ) {
        setSkillDropdownOpen(false);
      }
      if (
        iconPickerOpen &&
        iconPickerRef.current &&
        !iconPickerRef.current.contains(target)
      ) {
        setIconPickerOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [skillDropdownOpen, iconPickerOpen]);

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
      onClose();
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
    onClose,
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

  const isFormValid = draft.name.trim() && draft.system_prompt.trim();

  const title = editingPreset
    ? editingPreset.scope === "global"
      ? t("personaPresets.editOfficial", "编辑官方角色")
      : t("personaPresets.editMine", "编辑我的角色")
    : editorScope === "global"
      ? t("personaPresets.publishOfficial", "发布官方角色")
      : t("personaPresets.createMine", "新建我的角色");

  const subtitle =
    editorScope === "global"
      ? t(
          "personaPresets.officialHint",
          "官方角色会展示给所有用户，建议补全简介、标签和可用技能。",
        )
      : t("personaPresets.createHint", "定义角色的行为、语气和能力边界");

  return (
    <EditorSidebar
      open={showModal}
      onClose={onClose}
      title={title}
      subtitle={subtitle}
      icon={editingPreset ? <Pencil size={16} /> : <Plus size={16} />}
      footer={
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="btn-secondary">
            {t("common.cancel", "取消")}
          </button>
          <button
            onClick={handleSave}
            disabled={isMutating || !isFormValid}
            className="btn-primary disabled:opacity-50"
          >
            {isMutating ? <LoadingSpinner size="sm" /> : <Save size={16} />}
            {t("common.save", "保存")}
          </button>
        </div>
      }
    >
      <div className="es-form">
        {/* Profile: Avatar + Name + Description */}
        <div className="ppe-profile-section">
          <div className="ppe-avatar-upload">
            <div
              className="ppe-avatar-preview"
              onClick={() =>
                !draft.avatar &&
                !isUploadingAvatar &&
                avatarInputRef.current?.click()
              }
            >
              {isPersonaImageAvatar(draft.avatar) ? (
                <>
                  <PersonaAvatarImage
                    avatar={draft.avatar}
                    alt=""
                    className="ppe-avatar-img"
                    onError={() =>
                      setDraft((prev) => ({ ...prev, avatar: "" }))
                    }
                  />
                  <button
                    type="button"
                    className="ppe-avatar-remove"
                    onClick={(e) => {
                      e.stopPropagation();
                      setDraft((prev) => ({ ...prev, avatar: "" }));
                    }}
                    title={t("common.remove", "移除")}
                  >
                    <X size={12} />
                  </button>
                </>
              ) : draft.avatar ? (
                <>
                  <div className="ppe-avatar-placeholder">
                    <PersonaAvatarIcon avatar={draft.avatar} size={20} />
                  </div>
                  <button
                    type="button"
                    className="ppe-avatar-remove"
                    onClick={(e) => {
                      e.stopPropagation();
                      setDraft((prev) => ({ ...prev, avatar: "" }));
                    }}
                    title={t("common.remove", "移除")}
                  >
                    <X size={12} />
                  </button>
                </>
              ) : (
                <div className="ppe-avatar-placeholder">
                  <Camera size={18} />
                </div>
              )}
              {isUploadingAvatar && (
                <div className="ppe-avatar-uploading">
                  <Loader2 size={16} className="animate-spin" />
                </div>
              )}
            </div>
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
            <div ref={iconPickerRef} className="relative">
              <button
                type="button"
                className="ppe-avatar-hint-btn"
                disabled={isUploadingAvatar}
                onClick={() => setIconPickerOpen((v) => !v)}
              >
                <Smile size={12} />
                {t("personaPresets.pickIcon", "选择图标")}
              </button>
              {iconPickerOpen && (
                <div className="ppe-icon-picker">
                  {AVATAR_ICONS.map((item) => {
                    const Icon = item.icon;
                    return (
                      <button
                        key={item.key}
                        type="button"
                        className="ppe-icon-picker-item"
                        style={
                          {
                            "--icon-color": item.color,
                            "--icon-bg": item.bg,
                          } as React.CSSProperties
                        }
                        onClick={() => {
                          setDraft((prev) => ({
                            ...prev,
                            avatar: getPersonaAvatarIconValue(item.key),
                          }));
                          setIconPickerOpen(false);
                        }}
                        title={item.label}
                      >
                        <Icon size={15} style={{ color: item.color }} />
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          <div className="ppe-profile-fields">
            <div className="ppe-field">
              <label className="ppe-label">
                {t("personaPresets.name", "名称")}
                <span className="ppe-required">*</span>
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
            <div className="ppe-field">
              <label className="ppe-label">
                {t("personaPresets.description", "简介")}
              </label>
              <input
                value={draft.description}
                onChange={(e) =>
                  setDraft((prev) => ({ ...prev, description: e.target.value }))
                }
                className="ppe-input"
                placeholder={t(
                  "personaPresets.descriptionPlaceholder",
                  "简短描述角色的能力和特点",
                )}
              />
            </div>
          </div>
        </div>

        {/* Admin: Scope & Status */}
        {canAdmin && (
          <div
            className="ppe-section ppe-field-animated"
            style={{ animationDelay: "0ms" }}
          >
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="ppe-field">
                <label className="ppe-label">
                  {t("personaPresets.scope", "范围")}
                </label>
                <select
                  value={editorScope}
                  onChange={(event) =>
                    setEditorScope(event.target.value as "user" | "global")
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
                      setEditorStatus(event.target.value as PersonaPresetStatus)
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

        {/* System Prompt */}
        <div className="ppe-field">
          <label className="ppe-label">
            <MessageSquare size={13} className="ppe-label-icon" />
            {t("personaPresets.systemPrompt", "系统提示词")}
            <span className="ppe-required">*</span>
          </label>
          <div className="ppe-textarea-wrap">
            <textarea
              value={draft.system_prompt}
              onChange={(e) =>
                setDraft((prev) => ({ ...prev, system_prompt: e.target.value }))
              }
              rows={8}
              className="ppe-textarea"
              placeholder={t(
                "personaPresets.systemPromptPlaceholder",
                "定义角色的行为、语气和能力边界...",
              )}
            />
            <div className="ppe-char-counter">{draft.system_prompt.length}</div>
          </div>
        </div>

        {/* Tags + Skills */}
        <div className="ppe-meta-grid">
          <div className="ppe-field">
            <label className="ppe-label">
              <Tag size={13} className="ppe-label-icon" />
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
                "写作, 翻译, 代码",
              )}
            />
            {draft.tags.trim() && (
              <div className="ppe-chip-row">
                {draft.tags
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean)
                  .map((tag) => (
                    <span key={tag} className="ppe-tag-chip">
                      {tag}
                    </span>
                  ))}
              </div>
            )}
          </div>

          <div className="ppe-field">
            <label className="ppe-label">
              <Sparkles size={13} className="ppe-label-icon" />
              {t("personaPresets.skillsInput", "Skills")}
            </label>
            <div ref={skillDropdownRef} className="relative">
              <button
                type="button"
                onClick={() => {
                  setSkillDropdownOpen((v) => !v);
                  setSkillSearch("");
                }}
                className={`ppe-skill-trigger ${
                  skillDropdownOpen ? "ppe-skill-trigger--open" : ""
                }`}
              >
                {draft.skill_names.length > 0 ? (
                  <span className="ppe-skill-trigger__count">
                    <Sparkles size={12} />
                    {t("personaPresets.skillCount", "{{count}} 个技能已选择", {
                      count: draft.skill_names.length,
                    })}
                  </span>
                ) : (
                  <span className="ppe-skill-trigger__placeholder">
                    {t("personaPresets.skillsInputPlaceholder", "选择技能...")}
                  </span>
                )}
                <ChevronDown
                  size={14}
                  className={`ppe-skill-trigger__chevron ${
                    skillDropdownOpen ? "rotate-180" : ""
                  }`}
                />
              </button>

              {draft.skill_names.length > 0 && !skillDropdownOpen && (
                <div className="ppe-skill-selected-area">
                  {draft.skill_names.map((name) => (
                    <span key={name} className="ppe-skill-chip">
                      {name}
                      <X
                        size={11}
                        className="ppe-skill-chip-remove"
                        onClick={() =>
                          setDraft((prev) => ({
                            ...prev,
                            skill_names: prev.skill_names.filter(
                              (n) => n !== name,
                            ),
                          }))
                        }
                      />
                    </span>
                  ))}
                </div>
              )}

              {skillDropdownOpen && (
                <div className="ppe-skill-dropdown">
                  <div className="ppe-skill-dropdown__header">
                    <div className="ppe-skill-dropdown__search-wrap">
                      <Search
                        size={14}
                        className="ppe-skill-dropdown__search-icon"
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
                    {draft.skill_names.length > 0 && (
                      <button
                        type="button"
                        className="ppe-skill-dropdown__clear-all"
                        onClick={() =>
                          setDraft((prev) => ({ ...prev, skill_names: [] }))
                        }
                      >
                        {t("common.clearAll", "清除全部")}
                      </button>
                    )}
                  </div>

                  {draft.skill_names.length > 0 && (
                    <div className="ppe-skill-selected-bar">
                      {draft.skill_names.map((name) => (
                        <span key={name} className="ppe-skill-chip">
                          {name}
                          <X
                            size={11}
                            className="ppe-skill-chip-remove"
                            onClick={() =>
                              setDraft((prev) => ({
                                ...prev,
                                skill_names: prev.skill_names.filter(
                                  (n) => n !== name,
                                ),
                              }))
                            }
                          />
                        </span>
                      ))}
                    </div>
                  )}

                  <div className="ppe-skill-dropdown__list">
                    {displayedSkills.length > 0 ? (
                      displayedSkills.map((skill) => {
                        const isSelected = draft.skill_names.includes(
                          skill.name,
                        );
                        return (
                          <button
                            key={skill.name}
                            type="button"
                            onClick={() => {
                              setDraft((prev) => ({
                                ...prev,
                                skill_names: isSelected
                                  ? prev.skill_names.filter(
                                      (n) => n !== skill.name,
                                    )
                                  : [...prev.skill_names, skill.name],
                              }));
                            }}
                            className={`ppe-skill-option ${
                              isSelected ? "ppe-skill-option--selected" : ""
                            }`}
                          >
                            <div className="ppe-skill-option__check-ring">
                              {isSelected ? (
                                <Check
                                  size={12}
                                  className="ppe-skill-option__check-icon"
                                />
                              ) : (
                                <Plus
                                  size={12}
                                  className="ppe-skill-option__plus-icon"
                                />
                              )}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="text-sm font-medium truncate">
                                {skill.name}
                              </div>
                              {skill.description && (
                                <div className="text-[11px] text-[var(--theme-text-secondary)] truncate mt-0.5">
                                  {skill.description}
                                </div>
                              )}
                            </div>
                          </button>
                        );
                      })
                    ) : (
                      <div className="ppe-skill-dropdown__empty">
                        <Sparkles
                          size={20}
                          className="ppe-skill-dropdown__empty-icon"
                        />
                        <span>
                          {t("skills.noMatchingSkills", "没有匹配的技能")}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </EditorSidebar>
  );
}
