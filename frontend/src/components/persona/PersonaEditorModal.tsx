import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { GlassSelect } from "../common/GlassSelect";
import { Plus, Pencil, Sparkles, Tag, Save, MessageSquare, Puzzle, Server } from "lucide-react";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { EditorSidebar } from "../common/EditorSidebar";
import toast from "react-hot-toast";
import { mcpApi } from "../../services/api/mcp";
import { pluginApi } from "../../services/api/plugin";
import {
  buildPersonaPresetPayload,
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
    plugin_names: [...(editingPreset?.plugin_names || [])] as string[],
    mcp_server_names: [...(editingPreset?.mcp_server_names || [])] as string[],
  });

  const [skillDropdownOpen, setSkillDropdownOpen] = useState(false);
  const [pluginDropdownOpen, setPluginDropdownOpen] = useState(false);
  const [mcpDropdownOpen, setMcpDropdownOpen] = useState(false);
  const [pluginOptions, setPluginOptions] = useState<BindingOption[]>([]);
  const [mcpOptions, setMcpOptions] = useState<BindingOption[]>([]);
  const [bindingsLoading, setBindingsLoading] = useState(false);

  useEffect(() => {
    if (!showModal) return;
    let cancelled = false;
    setBindingsLoading(true);
    void (async () => {
      try {
        const [installs, mcpList] = await Promise.all([
          pluginApi.listInstalled(),
          mcpApi.list(),
        ]);
        if (cancelled) return;
        setPluginOptions(
          (installs.installs ?? []).map((record) => ({
            name: record.plugin_name,
            description: null,
          })),
        );
        setMcpOptions(
          (mcpList.servers ?? [])
            .filter((server) => server.enabled)
            .map((server) => ({
              name: server.name,
              description: server.source_plugin
                ? t("personaPresets.mcpFromPlugin", { name: server.source_plugin })
                : null,
            })),
        );
      } catch {
        if (!cancelled) {
          setPluginOptions([]);
          setMcpOptions([]);
        }
      } finally {
        if (!cancelled) setBindingsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [showModal, t]);

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
        starter_prompts: starterPromptsToDraftRows(
          editingPreset?.starter_prompts,
        ),
        tags: editingPreset?.tags.join(", ") || "",
        skill_names: [...(editingPreset?.skill_names || [])] as string[],
        plugin_names: [...(editingPreset?.plugin_names || [])] as string[],
        mcp_server_names: [...(editingPreset?.mcp_server_names || [])] as string[],
      });
      setSkillDropdownOpen(false);
    }
  }, [showModal, editingPreset, initialScope]);

  const handleSave = useCallback(async () => {
    if (!draft.name.trim() || !draft.system_prompt.trim()) return;
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
      plugin_names: draft.plugin_names,
      mcp_server_names: draft.mcp_server_names,
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
    if (!saved) {
      toast.error(
        editingPreset
          ? t("personaPresets.updateFailed", "角色更新失败")
          : t("personaPresets.createFailed", "角色创建失败"),
      );
      return;
    }

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
            {isMutating ? (
              <LoadingSpinner
                size="sm"
                color="text-white dark:text-stone-900"
              />
            ) : (
              <Save size={16} />
            )}
            {t("common.save", "保存")}
          </button>
        </div>
      }
    >
      <div className="es-form">
        {/* Profile: Avatar + Name + Description */}
        <div className="ppe-profile-section">
          <AvatarSection draft={draft} onDraftChange={setDraft} />

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
            <div className="grid gap-2 sm:gap-3 sm:grid-cols-2 ppe-admin-grid">
              <div className="ppe-field">
                <label className="ppe-label">
                  {t("personaPresets.scope", "范围")}
                </label>
                <GlassSelect
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
                  <GlassSelect
                    value={editorStatus}
                    onChange={(v) => setEditorStatus(v as PersonaPresetStatus)}
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
          </div>

          <div className="ppe-field">
            <label className="ppe-label">
              <Puzzle size={13} className="ppe-label-icon" />
              {t("personaPresets.pluginsInput", "插件")}
            </label>
            <PersonaEditorBindingSelector
              options={pluginOptions}
              selected={draft.plugin_names}
              onChange={(updater) =>
                setDraft((prev) => ({
                  ...prev,
                  plugin_names: updater(prev.plugin_names),
                }))
              }
              open={pluginDropdownOpen}
              onOpenChange={setPluginDropdownOpen}
              icon={<Puzzle size={12} />}
              countLabelKey="personaPresets.pluginCount"
              placeholderKey="personaPresets.pluginsInputPlaceholder"
              searchPlaceholderKey="personaPresets.pluginsSearchPlaceholder"
              emptyKey="personaPresets.noPlugins"
              loading={bindingsLoading}
            />
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
            />
          </div>
        </div>
      </div>
    </EditorSidebar>
  );
}
