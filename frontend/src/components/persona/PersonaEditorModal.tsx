import { useCallback, useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button, Select } from "../common/ui";
import {
  Plus,
  Pencil,
  Sparkles,
  Tag,
  Save,
  MessageSquare,
  Server,
  TriangleAlert,
} from "lucide-react";
import { PanelFooterActions } from "../common";
import { ConfigPanelErrorCallout } from "../panels/ConfigPanelErrorCallout";
import { EditorSidebar } from "../common/EditorSidebar";
import toast from "react-hot-toast";
import { mcpApi } from "../../services/api/mcp";
import { skillApi } from "../../services/api/skill";
import {
  buildPersonaPresetPayload,
  computeMissingBindings,
  draftRowsToStarterPrompts,
  starterPromptsToDraftRows,
} from "./personaPresetEditor";
import { AvatarSection } from "./PersonaEditorAvatarSection";
import {
  PersonaEditorBindingSelector,
  type BindingOption,
} from "./PersonaEditorBindingSelector";
import { SkillSelector } from "./PersonaEditorSkillSelector";
import { StarterPromptsEditor } from "./PersonaEditorStarterPrompts";
import type {
  PersonaEditorModalProps,
  PersonaEditorDraft,
  PersonaPresetStatus,
} from "./PersonaEditorTypes";

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
  const fieldId = useId();
  const nameInputRef = useRef<HTMLInputElement>(null);
  const formRef = useRef<HTMLDivElement>(null);
  const session = useRef(0);
  const pendingSave = useRef(false);
  const [avatarSession, setAvatarSession] = useState(0);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(false);
  const [avatarUploading, setAvatarUploading] = useState(false);
  const [editorScope, setEditorScope] = useState<"user" | "global">(
    initialScope,
  );
  const [editorStatus, setEditorStatus] = useState<PersonaPresetStatus>(
    editingPreset?.status ??
      (initialScope === "global" ? "published" : "draft"),
  );
  const [draft, setDraft] = useState<PersonaEditorDraft>({
    name: editingPreset?.name || "",
    description: editingPreset?.description || "",
    avatar: editingPreset?.avatar || "",
    system_prompt: editingPreset?.system_prompt || "",
    starter_prompts: starterPromptsToDraftRows(editingPreset?.starter_prompts),
    tags: editingPreset?.tags.join(", ") || "",
    skill_names: [...(editingPreset?.skill_names || [])] as string[],
    mcp_server_names: [...(editingPreset?.mcp_server_names || [])] as string[],
  });

  const [skillDropdownOpen, setSkillDropdownOpen] = useState(false);
  const [mcpDropdownOpen, setMcpDropdownOpen] = useState(false);
  const [mcpOptions, setMcpOptions] = useState<BindingOption[]>([]);
  const [installedSkillNames, setInstalledSkillNames] = useState<string[]>([]);
  const [bindingsLoading, setBindingsLoading] = useState(true);
  const [bindingsError, setBindingsError] = useState(false);
  const [bindingsAttempt, setBindingsAttempt] = useState(0);
  const [bindingsReady, setBindingsReady] = useState(false);
  const [loadedPreset, setLoadedPreset] = useState<typeof editingPreset>();

  useEffect(() => {
    if (!showModal) return;
    let cancelled = false;
    setBindingsLoading(true);
    setBindingsError(false);
    setBindingsReady(false);
    void (async () => {
      try {
        const declaredSkills = editingPreset?.skill_names ?? [];
        const readSkills = async () => {
          const names: string[] = [];
          let skip = 0;
          while (
            !cancelled &&
            declaredSkills.some((name) => !names.includes(name))
          ) {
            const page = await skillApi.list({ skip, limit: 100 });
            names.push(...page.skills.map((skill) => skill.skill_name));
            skip += page.skills.length;
            if (!page.skills.length || skip >= page.total) break;
          }
          return names;
        };
        const [mcpList, skillNames] = await Promise.all([
          mcpApi.list(),
          readSkills(),
        ]);
        if (cancelled) return;
        setMcpOptions(
          (mcpList.servers ?? [])
            .filter((server) => server.enabled)
            .map((server) => ({ name: server.name, description: null })),
        );
        setInstalledSkillNames(skillNames);
        setLoadedPreset(editingPreset);
        setBindingsReady(true);
      } catch {
        if (!cancelled) setBindingsError(true);
      } finally {
        if (!cancelled) setBindingsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [showModal, editingPreset, bindingsAttempt]);

  const canCheckBindings = bindingsReady && loadedPreset === editingPreset;

  // 编辑既有预设时，绑定里当前用户不可用的部分（技能未安装 / MCP 不可见）
  const missingSkills = computeMissingBindings(
    editingPreset?.skill_names,
    installedSkillNames,
  );
  const missingMcpServers = computeMissingBindings(
    editingPreset?.mcp_server_names,
    mcpOptions.map((option) => option.name),
  );

  useEffect(() => {
    session.current += 1;
    pendingSave.current = false;
    setAvatarSession(session.current);
    setSaving(false);
    setSaveError(false);
    setAvatarUploading(false);
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
        starter_prompts: starterPromptsToDraftRows(
          editingPreset?.starter_prompts,
        ),
        tags: editingPreset?.tags.join(", ") || "",
        skill_names: [...(editingPreset?.skill_names || [])] as string[],
        mcp_server_names: [
          ...(editingPreset?.mcp_server_names || []),
        ] as string[],
      });
      setSkillDropdownOpen(false);
      setMcpDropdownOpen(false);
    }
    return () => {
      session.current += 1;
    };
  }, [showModal, editingPreset, initialScope]);

  const handleSave = useCallback(async () => {
    if (
      !showModal ||
      pendingSave.current ||
      isMutating ||
      avatarUploading ||
      !draft.name.trim() ||
      !draft.system_prompt.trim()
    )
      return;
    const owner = session.current;
    pendingSave.current = true;
    formRef.current?.focus({ preventScroll: true });
    setSaving(true);
    setSaveError(false);
    setSkillDropdownOpen(false);
    setMcpDropdownOpen(false);
    const normalizedDraft = {
      name: draft.name.trim(),
      description: draft.description.trim(),
      avatar: draft.avatar,
      system_prompt: draft.system_prompt.trim(),
      starter_prompts: draftRowsToStarterPrompts(draft.starter_prompts),
      tags: draft.tags
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      skill_names: draft.skill_names,
      mcp_server_names: draft.mcp_server_names,
    };

    try {
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
      if (owner !== session.current) return;
      if (!saved) {
        setSaveError(true);
        return;
      }
      onClose();
      toast.success(
        t(
          editingPreset
            ? "personaPresets.updateSuccess"
            : "personaPresets.createSuccess",
          { name: normalizedDraft.name },
        ),
      );
    } catch {
      if (owner === session.current) setSaveError(true);
    } finally {
      if (owner === session.current) {
        pendingSave.current = false;
        setSaving(false);
      }
    }
  }, [
    showModal,
    isMutating,
    avatarUploading,
    onClose,
    createPreset,
    draft,
    editingPreset,
    editorScope,
    editorStatus,
    t,
    updatePreset,
  ]);

  const busy = saving;
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
        <div className="flex flex-col gap-3">
          {saveError && (
            <ConfigPanelErrorCallout
              message={t(
                editingPreset
                  ? "personaPresets.updateFailed"
                  : "personaPresets.createFailed",
              )}
            />
          )}
          <PanelFooterActions align="between">
            <Button onClick={onClose}>{t("common.cancel")}</Button>
            <span className="panel-footer-actions__spacer" />
            <Button
              variant="primary"
              onClick={handleSave}
              disabled={busy || isMutating || avatarUploading || !isFormValid}
              loading={busy}
              leftIcon={<Save size={14} />}
            >
              <span role={busy ? "status" : undefined}>
                {busy
                  ? t("common.saving")
                  : saveError
                    ? t("common.retry")
                    : t("common.save")}
              </span>
            </Button>
          </PanelFooterActions>
        </div>
      }
    >
      <div
        ref={formRef}
        tabIndex={-1}
        className="es-form min-w-0"
        aria-busy={busy}
      >
        <fieldset disabled={busy} className="contents">
          <p className="text-12 leading-relaxed text-theme-text-secondary">
            {subtitle}
          </p>
          {/* Profile: Avatar + Name + Description */}
          <div className="ppe-profile-section">
            <AvatarSection
              key={avatarSession}
              avatar={draft.avatar}
              onAvatarChange={(avatar) =>
                setDraft((prev) => ({ ...prev, avatar }))
              }
              onUploadingChange={setAvatarUploading}
            />

            <div className="ppe-profile-fields">
              <div className="ppe-field">
                <label className="ppe-label" htmlFor={`${fieldId}-name`}>
                  {t("personaPresets.name", "名称")}
                  <span className="ppe-required" aria-hidden="true">
                    *
                  </span>
                </label>
                <input
                  id={`${fieldId}-name`}
                  ref={nameInputRef}
                  required
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
                <label className="ppe-label" htmlFor={`${fieldId}-description`}>
                  {t("personaPresets.description", "简介")}
                </label>
                <input
                  id={`${fieldId}-description`}
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
            </div>
          </div>

          {/* Admin: Scope & Status */}
          {canAdmin && (
            <div
              className="ppe-section ppe-field-animated"
              style={{ animationDelay: "0ms" }}
            >
              <div className="grid gap-2 sm:gap-3 sm:grid-cols-2 ppe-admin-grid">
                <div className="ppe-field">
                  <label className="ppe-label">
                    {t("personaPresets.scope", "范围")}
                  </label>
                  <Select
                    disabled={busy}
                    ariaLabel={t("personaPresets.scope")}
                    triggerClassName="glass-input es-select-btn"
                    dropdownClassName="glass-select-dropdown"
                    value={editorScope}
                    onChange={(v) => setEditorScope(v as "user" | "global")}
                    options={[
                      {
                        value: "user",
                        label: t("personaPresets.mine", "我的"),
                      },
                      {
                        value: "global",
                        label: t("personaPresets.official", "官方"),
                      },
                    ]}
                  />
                </div>
                {editorScope === "global" && (
                  <div className="ppe-field">
                    <label className="ppe-label">
                      {t("personaPresets.status", "状态")}
                    </label>
                    <Select
                      disabled={busy}
                      ariaLabel={t("personaPresets.status")}
                      triggerClassName="glass-input es-select-btn"
                      dropdownClassName="glass-select-dropdown"
                      value={editorStatus}
                      onChange={(v) =>
                        setEditorStatus(v as PersonaPresetStatus)
                      }
                      options={[
                        {
                          value: "draft",
                          label: t("personaPresets.draft", "草稿"),
                        },
                        {
                          value: "published",
                          label: t("personaPresets.published", "已发布"),
                        },
                        {
                          value: "archived",
                          label: t("personaPresets.archived", "已归档"),
                        },
                      ]}
                    />
                  </div>
                )}
              </div>
            </div>
          )}

          {/* System Prompt */}
          <div className="ppe-field">
            <label className="ppe-label" htmlFor={`${fieldId}-system_prompt`}>
              <MessageSquare size={13} className="ppe-label-icon" />
              {t("personaPresets.systemPrompt", "系统提示词")}
              <span className="ppe-required" aria-hidden="true">
                *
              </span>
            </label>
            <div className="ppe-textarea-wrap">
              <textarea
                id={`${fieldId}-system_prompt`}
                required
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
          </div>

          {/* Starter Prompts */}
          <StarterPromptsEditor
            prompts={draft.starter_prompts}
            onChange={(updater) =>
              setDraft((prev) => ({
                ...prev,
                starter_prompts: updater(prev.starter_prompts),
              }))
            }
          />

          {bindingsError && (
            <div
              role="alert"
              className="flex flex-wrap items-center justify-between gap-2 text-12 text-theme-text-secondary"
            >
              <span>{t("common.loadFailed")}</span>
              <Button
                size="sm"
                className="!min-h-11"
                onClick={() => {
                  nameInputRef.current?.focus();
                  setBindingsAttempt((attempt) => attempt + 1);
                }}
              >
                {t("common.retry")}
              </Button>
            </div>
          )}

          {/* Tags + Skills */}
          <div className="ppe-meta-grid">
            <div className="ppe-field">
              <label className="ppe-label" htmlFor={`${fieldId}-tags`}>
                <Tag size={13} className="ppe-label-icon" />
                {t("personaPresets.tagsInput", "标签")}
              </label>
              <input
                id={`${fieldId}-tags`}
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
              <SkillSelector
                skillNames={draft.skill_names}
                onSkillNamesChange={(updater) =>
                  setDraft((prev) => ({
                    ...prev,
                    skill_names: updater(prev.skill_names),
                  }))
                }
                open={skillDropdownOpen}
                onOpenChange={setSkillDropdownOpen}
              />
              {canCheckBindings && missingSkills.length > 0 && (
                <p className="mt-1.5 flex items-start gap-1 text-11 leading-relaxed text-amber-600/90 dark:text-amber-400/90">
                  <TriangleAlert
                    size={11}
                    className="mt-0.5 shrink-0 opacity-80"
                  />
                  {t("personaPresets.missingSkillsHint", {
                    names: missingSkills.join("、"),
                  })}
                </p>
              )}
            </div>

            <div className="ppe-field">
              <label className="ppe-label">
                <Server size={13} className="ppe-label-icon" />
                {t("personaPresets.mcpServersInput", "MCP 服务")}
              </label>
              <PersonaEditorBindingSelector
                options={mcpOptions}
                selected={draft.mcp_server_names}
                onChange={(updater) =>
                  setDraft((prev) => ({
                    ...prev,
                    mcp_server_names: updater(prev.mcp_server_names),
                  }))
                }
                open={mcpDropdownOpen}
                onOpenChange={setMcpDropdownOpen}
                icon={<Server size={12} />}
                countLabelKey="personaPresets.mcpServerCount"
                placeholderKey="personaPresets.mcpServersInputPlaceholder"
                searchPlaceholderKey="personaPresets.mcpSearchPlaceholder"
                emptyKey="personaPresets.noMcpServers"
                loading={bindingsLoading}
                disabled={!canCheckBindings}
              />
              {canCheckBindings && missingMcpServers.length > 0 && (
                <p className="mt-1.5 flex items-start gap-1 text-11 leading-relaxed text-amber-600/90 dark:text-amber-400/90">
                  <TriangleAlert
                    size={11}
                    className="mt-0.5 shrink-0 opacity-80"
                  />
                  {t("personaPresets.missingMcpHint", {
                    names: missingMcpServers.join("、"),
                  })}
                </p>
              )}
            </div>
          </div>
        </fieldset>
      </div>
    </EditorSidebar>
  );
}
