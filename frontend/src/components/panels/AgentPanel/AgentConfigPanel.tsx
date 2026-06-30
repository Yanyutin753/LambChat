/**
 * Agent 配置管理面板组件
 * 管理员配置全局 Agent 启用/禁用和角色分配
 */

import { useState, useEffect, useCallback } from "react";
import { Bot, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import i18n from "../../../i18n";
import toast from "react-hot-toast";
import { Button } from "../../common";
import { PanelHeader } from "../../common/PanelHeader";
import { AgentIcon } from "../../agent/AgentIcon";
import { AgentPanelSkeleton } from "../../skeletons";
import { agentConfigApi, roleApi, agentApi } from "../../../services/api";
import { useAuth } from "../../../hooks/useAuth";
import { useExtensionContributions } from "../../../hooks/useExtensionContributions";
import { buildAgentCategoryContributions } from "../../../extensions";
import { Permission } from "../../../types";
import type { AgentConfig, Role, AgentInfo } from "../../../types";
import {
  resolveAgentDescription,
  resolveAgentDisplayName,
} from "../../agent/agentCatalog";
import { ConfigPanelErrorCallout } from "../ConfigPanelErrorCallout";
import { groupAgentsByPluginCategory } from "./agentCategoryGroups";

import { GlobalAgentTab, RolesAgentTab } from "./tabs";

type AgentTabType = "global" | "roles";

/**
 * Agent 配置面板主组件
 */
export function AgentConfigPanel() {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const canManageAgents = hasPermission(Permission.AGENT_ADMIN);
  const { plugins: runtimePlugins } = useExtensionContributions();
  const agentCategories = buildAgentCategoryContributions(runtimePlugins);
  const [activeTab, setActiveTab] = useState<AgentTabType>("global");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 数据状态
  const [globalAgents, setGlobalAgents] = useState<AgentConfig[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [roleAgentsMap, setRoleAgentsMap] = useState<Record<string, string[]>>(
    {},
  );
  const [availableAgents, setAvailableAgents] = useState<AgentInfo[]>([]);

  // 加载数据
  const loadData = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      // 并行加载所有数据
      const [globalConfig, roleList, agentList] = await Promise.all([
        canManageAgents
          ? agentConfigApi.getCatalogConfig()
          : Promise.resolve(null),
        roleApi.list({ limit: 200 }),
        agentApi.list(),
      ]);

      // 管理员使用全局配置的全部 agent（用于角色分配），非管理员使用过滤后的列表
      setAvailableAgents(
        canManageAgents && globalConfig
          ? globalConfig.agents
              .filter((a) => a.enabled)
              .map((a) => ({
                id: a.id,
                name: a.name,
                description: a.description,
                version: "",
                icon: a.icon,
                sort_order: a.sort_order,
                category: a.category,
                labels: a.labels,
              }))
          : agentList.agents || [],
      );

      // 设置全局 agents
      if (globalConfig) {
        setGlobalAgents(globalConfig.agents || []);
      } else {
        // 非管理员只看可用 agents
        setGlobalAgents(
          (agentList.agents || []).map((a) => ({
            id: a.id,
            name: a.name,
            description: a.description,
            enabled: true,
            icon: a.icon,
            sort_order: a.sort_order,
            category: a.category,
            labels: a.labels,
          })),
        );
      }

      // 设置角色列表
      setRoles(roleList.roles || []);

      // 加载角色-agents 映射
      if (canManageAgents) {
        const roleAgentPromises = (roleList.roles || []).map(async (role) => {
          try {
            const assignment = await agentConfigApi.getRoleAgents(role.id);
            return { roleId: role.id, agents: assignment.allowed_agents };
          } catch {
            return { roleId: role.id, agents: [] };
          }
        });
        const roleAgentResults = await Promise.all(roleAgentPromises);
        const map: Record<string, string[]> = {};
        roleAgentResults.forEach(({ roleId, agents }) => {
          map[roleId] = agents;
        });
        setRoleAgentsMap(map);
      }
    } catch (err) {
      const errorMsg = (err as Error).message || t("agentConfig.loadFailed");
      setError(errorMsg);
      toast.error(errorMsg);
    } finally {
      setIsLoading(false);
    }
  }, [canManageAgents, t]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // 更新全局配置
  const handleUpdateGlobalConfig = async (agents: AgentConfig[]) => {
    if (!canManageAgents) return;
    setIsSaving(true);
    try {
      await agentConfigApi.updateCatalogConfig(
        agents.map((agent) => ({
          ...agent,
          icon: agent.icon || "Bot",
          sort_order: agent.sort_order ?? 100,
          labels: agent.labels || {},
        })),
      );
      setGlobalAgents(agents);
      setAvailableAgents(
        agents
          .filter((agent) => agent.enabled)
          .map((agent) => ({
            id: agent.id,
            name: agent.name,
            description: agent.description,
            version: "",
            icon: agent.icon,
            sort_order: agent.sort_order,
            category: agent.category,
            labels: agent.labels,
          })),
      );
      toast.success(t("agentConfig.saveSuccess"));
    } catch (err) {
      toast.error((err as Error).message || t("agentConfig.saveFailed"));
      throw err;
    } finally {
      setIsSaving(false);
    }
  };

  // 更新角色配置
  const handleUpdateRoleAgents = async (roleId: string, agentIds: string[]) => {
    if (!canManageAgents) return;
    try {
      await agentConfigApi.updateRoleAgents(roleId, agentIds);
      setRoleAgentsMap((prev) => ({ ...prev, [roleId]: agentIds }));
      toast.success(t("agentConfig.saveSuccess"));
    } catch (err) {
      toast.error((err as Error).message || t("agentConfig.saveFailed"));
      throw err;
    }
  };

  // 刷新数据
  const handleRefresh = () => {
    loadData();
  };

  if (isLoading) {
    return <AgentPanelSkeleton />;
  }

  return (
    <div className="glass-shell flex h-full flex-col min-h-0">
      {/* 头部 */}
      <PanelHeader
        title={t("agentConfig.title")}
        subtitle={t("agentConfig.subtitle")}
        icon={<Bot size={24} className="text-stone-600 dark:text-stone-400" />}
        actions={
          <Button
            onClick={handleRefresh}
            leftIcon={<RefreshCw size={16} />}
            aria-label={t("common.refresh")}
          >
            <span className="hidden sm:inline text-sm">
              {t("common.refresh")}
            </span>
          </Button>
        }
      />

      {/* 错误提示 */}
      {error && (
        <ConfigPanelErrorCallout
          message={error}
          className="mx-4 mt-4 sm:mx-6"
        />
      )}

      {/* Tab 切换 */}
      {canManageAgents && (
        <div className="flex glass-divider px-2">
          <button
            onClick={() => setActiveTab("global")}
            className={`px-4 py-3.5 text-sm font-medium transition-all relative ${
              activeTab === "global"
                ? "text-stone-900 dark:text-stone-100"
                : "text-stone-500 hover:text-stone-700 dark:text-stone-400 dark:hover:text-stone-200"
            }`}
          >
            {activeTab === "global" && (
              <span className="absolute bottom-0 left-3 right-3 h-0.5 rounded-full bg-stone-600 dark:bg-stone-400" />
            )}
            {t("agentConfig.globalTab")}
          </button>
          <button
            onClick={() => setActiveTab("roles")}
            className={`px-4 py-3.5 text-sm font-medium transition-all relative ${
              activeTab === "roles"
                ? "text-stone-900 dark:text-stone-100"
                : "text-stone-500 hover:text-stone-700 dark:text-stone-400 dark:hover:text-stone-200"
            }`}
          >
            {activeTab === "roles" && (
              <span className="absolute bottom-0 left-3 right-3 h-0.5 rounded-full bg-stone-600 dark:bg-stone-400" />
            )}
            {t("agentConfig.rolesTab")}
          </button>
        </div>
      )}

      {/* 内容 */}
      <div className="flex-1 overflow-y-auto px-4 py-5 sm:px-6">
        {canManageAgents ? (
          activeTab === "global" ? (
            <GlobalAgentTab
              agents={globalAgents}
              onUpdate={handleUpdateGlobalConfig}
              isLoading={isLoading}
              isSaving={isSaving}
              agentCategories={agentCategories}
            />
          ) : (
            <RolesAgentTab
              roles={roles}
              roleAgentsMap={roleAgentsMap}
              availableAgents={availableAgents}
              onUpdate={handleUpdateRoleAgents}
              isLoading={isLoading}
              agentCategories={agentCategories}
            />
          )
        ) : (
          // 非管理员只显示可用 agents
          <div className="space-y-5">
            <p className="text-sm text-stone-500 dark:text-stone-400 px-1 leading-relaxed">
              {t("agentConfig.availableAgents")}
            </p>
            <div className="grid gap-4">
              {groupAgentsByPluginCategory(availableAgents, agentCategories).map((group) => (
                <section key={group.id} className="space-y-2">
                  <div className="flex items-center gap-2 px-1 text-xs font-medium uppercase tracking-wider text-theme-text-tertiary">
                    <AgentIcon icon={group.icon} size={14} />
                    <span>{t(group.label, group.label)}</span>
                  </div>
                  <div className="grid gap-3">
                    {group.agents.map((agent) => {
                const displayName = resolveAgentDisplayName(
                  agent,
                  i18n.language,
                  t,
                );
                const displayDescription = resolveAgentDescription(
                  agent,
                  i18n.language,
                  t,
                );
                return (
                  <div
                    key={agent.id}
                    className="flex items-center gap-3.5 glass-card rounded-xl p-4 transition-all duration-200 hover:shadow-[var(--glass-shadow-hover)]"
                  >
                    <div className="flex h-11 w-11 flex-shrink-0 items-center justify-center overflow-hidden rounded-xl bg-[var(--glass-bg-subtle)] ring-1 ring-[var(--glass-border)] shadow-sm">
                      <AgentIcon
                        icon={agent.icon || "Bot"}
                        size={20}
                        className="text-stone-600 dark:text-stone-400"
                      />
                    </div>
                    <div className="min-w-0 flex-1">
                      <h4 className="text-sm font-semibold text-stone-900 dark:text-stone-100 truncate tracking-tight font-serif">
                        {displayName}
                      </h4>
                      <p className="text-xs text-stone-500 dark:text-stone-400 truncate mt-0.5 hidden sm:block">
                        {displayDescription}
                      </p>
                    </div>
                  </div>
                );
                    })}
                  </div>
                </section>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default AgentConfigPanel;
