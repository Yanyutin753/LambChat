import { useState, useEffect, useCallback } from "react";
import { Pencil, Save } from "lucide-react";
import { useTranslation } from "react-i18next";
import i18n from "../../../../i18n";
import { AgentIcon } from "../../../agent/AgentIcon";
import { AgentIconSelect } from "../../../agent/AgentIconSelect";
import { EditorSidebar } from "../../../common/EditorSidebar";
import { Button, Input, PanelFooterActions, Textarea } from "../../../common";
import { AgentPanelSkeleton } from "../../../skeletons";
import {
  AGENT_CATALOG_LOCALES,
  resolveAgentDescription,
  resolveAgentDisplayName,
} from "../../../agent/agentCatalog";
import { ToggleSwitch } from "../shared/ToggleSwitch";
import { groupAgentsByPluginCategory } from "../agentCategoryGroups";
import type { CoreAgentCategoryContribution } from "../../../../extensions";
import type { AgentConfig, AgentCatalogLabels } from "../../../../types";

interface GlobalAgentTabProps {
  agents: AgentConfig[];
  onUpdate: (agents: AgentConfig[]) => Promise<void>;
  isLoading: boolean;
  isSaving: boolean;
  agentCategories?: readonly CoreAgentCategoryContribution[];
}

export function GlobalAgentTab({
  agents,
  onUpdate,
  isLoading,
  isSaving,
  agentCategories = [],
}: GlobalAgentTabProps) {
  const { t } = useTranslation();
  const [localAgents, setLocalAgents] = useState<AgentConfig[]>(agents);
  const [editingAgentId, setEditingAgentId] = useState<string | null>(null);
  const [activeLocale, setActiveLocale] = useState<string>(
    i18n.language?.split("-")[0] || "zh",
  );

  useEffect(() => {
    setLocalAgents(agents);
  }, [agents]);

  const toggleAgent = useCallback((agentId: string) => {
    setLocalAgents((prev) =>
      prev.map((a) => (a.id === agentId ? { ...a, enabled: !a.enabled } : a)),
    );
  }, []);

  const updateEditingAgent = useCallback(
    (patch: Partial<AgentConfig>) => {
      setLocalAgents((prev) =>
        prev.map((agent) =>
          agent.id === editingAgentId ? { ...agent, ...patch } : agent,
        ),
      );
    },
    [editingAgentId],
  );

  const updateEditingAgentLabel = useCallback(
    (locale: string, field: "name" | "description", value: string) => {
      setLocalAgents((prev) =>
        prev.map((agent) => {
          if (agent.id !== editingAgentId) return agent;
          const labels: AgentCatalogLabels = { ...(agent.labels || {}) };
          labels[locale] = {
            name: labels[locale]?.name || "",
            description: labels[locale]?.description || "",
            [field]: value,
          };
          return { ...agent, labels };
        }),
      );
    },
    [editingAgentId],
  );

  const editingAgent = localAgents.find((a) => a.id === editingAgentId) || null;
  const hasChanges = JSON.stringify(localAgents) !== JSON.stringify(agents);

  const handleSave = async () => {
    try {
      await onUpdate(localAgents);
    } catch (err) {
      console.error("Failed to save:", err);
    }
  };

  if (isLoading) {
    return <AgentPanelSkeleton />;
  }

  return (
    <div className="space-y-4">
      <p className="hidden px-1 text-sm leading-relaxed text-theme-text-secondary sm:block">
        {t("agentConfig.globalDescription")}
      </p>

      <div className="space-y-4">
        {groupAgentsByPluginCategory(localAgents, agentCategories).map((group) => (
          <section key={group.id} className="space-y-2">
            <div className="flex items-center gap-2 px-1 text-xs font-medium uppercase tracking-wider text-theme-text-tertiary">
              <AgentIcon icon={group.icon} size={14} />
              <span>{t(group.label, group.label)}</span>
            </div>
            <div className="glass-card divide-y divide-[var(--glass-border)] overflow-hidden rounded-xl">
        {group.agents.map((agent, index) => {
          const displayName = resolveAgentDisplayName(agent, i18n.language, t);
          const displayDescription = resolveAgentDescription(
            agent,
            i18n.language,
            t,
          );

          return (
            <div
              key={agent.id}
              className="group transition-colors duration-150 hover:bg-[var(--glass-bg-hover)]"
              style={{ animationDelay: `${index * 40}ms` }}
            >
              <div className="flex items-center justify-between gap-3 px-4 py-3.5">
                <button
                  type="button"
                  onClick={() => setEditingAgentId(agent.id)}
                  className="flex min-w-0 flex-1 items-center gap-3.5 text-left"
                >
                  <div className="flex size-10 flex-shrink-0 items-center justify-center overflow-hidden rounded-xl bg-[var(--glass-bg-subtle)] text-theme-text-secondary ring-1 ring-[var(--glass-border)] transition-all duration-200 group-hover:bg-[var(--glass-bg-hover)]">
                    <AgentIcon icon={agent.icon || "Bot"} size={20} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <h4 className="truncate text-sm font-medium tracking-tight text-theme-text">
                      {displayName}
                    </h4>
                    <p className="mt-0.5 hidden truncate text-xs text-theme-text-secondary sm:block">
                      {displayDescription}
                    </p>
                  </div>
                  <Pencil
                    size={14}
                    className="flex-shrink-0 text-theme-text-tertiary opacity-0 transition-opacity group-hover:opacity-100"
                  />
                </button>

                <ToggleSwitch
                  enabled={agent.enabled}
                  onToggle={() => toggleAgent(agent.id)}
                  ariaLabel={
                    agent.enabled
                      ? t("agentConfig.disableAgent", { name: displayName })
                      : t("agentConfig.enableAgent", { name: displayName })
                  }
                />
              </div>
            </div>
          );
        })}
            </div>
          </section>
        ))}
      </div>

      {hasChanges && (
        <div className="glass-divider mt-4 flex items-center justify-between pt-4">
          <span className="flex items-center gap-1.5 text-xs text-theme-text-tertiary">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse" />
            {localAgents.filter((a) => a.enabled).length} / {localAgents.length}{" "}
            {t("agentConfig.agentsEnabled", {
              count: localAgents.filter((a) => a.enabled).length,
            })}
          </span>
          <Button
            variant="primary"
            onClick={handleSave}
            loading={isSaving}
            leftIcon={<Save size={16} />}
            className="px-5 py-2.5 text-sm"
          >
            {t("common.save")}
          </Button>
        </div>
      )}

      {/* Editor Sidebar */}
      {editingAgent && (
        <EditorSidebar
          open={!!editingAgent}
          onClose={() => setEditingAgentId(null)}
          title={resolveAgentDisplayName(editingAgent, i18n.language, t)}
          icon={<AgentIcon icon={editingAgent.icon || "Bot"} size={18} />}
          footer={
            hasChanges ? (
              <PanelFooterActions>
                <Button onClick={() => setEditingAgentId(null)}>
                  {t("common.cancel")}
                </Button>
                <Button
                  variant="primary"
                  onClick={handleSave}
                  loading={isSaving}
                  leftIcon={<Save size={16} />}
                  className="px-5 py-2.5 text-sm"
                >
                  {t("common.save")}
                </Button>
              </PanelFooterActions>
            ) : undefined
          }
        >
          <div className="es-form">
            {/* Identity */}
            <div className="es-section">
              <div className="es-row">
                <div className="es-field">
                  <label className="es-label">
                    {t("agentConfig.agentIcon", "图标")}
                  </label>
                  <AgentIconSelect
                    value={editingAgent.icon || ""}
                    onChange={(value) => updateEditingAgent({ icon: value })}
                  />
                  <p className="es-hint">
                    {t(
                      "agentConfig.agentIconHint",
                      "支持 LobeHub 图标 slug（如 qwen、openai）、Lucide 图标名或 emoji",
                    )}
                  </p>
                </div>
                <div className="es-field">
                  <label className="es-label">
                    {t("agentConfig.sortOrder", "排序")}
                  </label>
                  <Input
                    type="number"
                    value={editingAgent.sort_order ?? 100}
                    onChange={(event) =>
                      updateEditingAgent({
                        sort_order: Number(event.target.value),
                      })
                    }
                    className="es-input tabular-nums"
                  />
                </div>
              </div>
            </div>

            {/* Localized Content */}
            <div className="es-section">
              <div className="flex items-center justify-between">
                <div className="es-section-title">
                  {t("agentConfig.localeContent", "多语言内容")}
                </div>
                <div className="flex gap-0.5">
                  {AGENT_CATALOG_LOCALES.map((locale) => (
                    <button
                      key={locale.code}
                      type="button"
                      onClick={() => setActiveLocale(locale.code)}
                      className={`rounded px-1.5 py-0.5 text-[11px] font-medium transition-colors duration-150 ${
                        activeLocale === locale.code
                          ? "bg-[var(--theme-primary-light)] text-[var(--theme-primary-hover)]"
                          : "text-theme-text-secondary hover:text-[var(--theme-primary)]"
                      }`}
                    >
                      {locale.code.toUpperCase()}
                    </button>
                  ))}
                </div>
              </div>
              <p className="es-hint" style={{ marginTop: "-0.25rem" }}>
                {t(
                  "agentConfig.localeHint",
                  "为不同语言的用户设置 Agent 的显示名称和描述，留空则使用默认翻译。",
                )}
              </p>

              <Input
                type="text"
                value={editingAgent.labels?.[activeLocale]?.name || ""}
                onChange={(event) =>
                  updateEditingAgentLabel(
                    activeLocale,
                    "name",
                    event.target.value,
                  )
                }
                placeholder={t("agentConfig.displayName", {
                  lng: activeLocale,
                  defaultValue:
                    activeLocale === "zh" ? "显示名称" : "Display Name",
                })}
                className="es-input"
              />

              <Textarea
                value={editingAgent.labels?.[activeLocale]?.description || ""}
                onChange={(event) =>
                  updateEditingAgentLabel(
                    activeLocale,
                    "description",
                    event.target.value,
                  )
                }
                placeholder={t("agentConfig.displayDescription", {
                  lng: activeLocale,
                  defaultValue: activeLocale === "zh" ? "描述" : "Description",
                })}
                rows={2}
                className="es-textarea resize-y"
              />
            </div>
          </div>
        </EditorSidebar>
      )}
    </div>
  );
}
