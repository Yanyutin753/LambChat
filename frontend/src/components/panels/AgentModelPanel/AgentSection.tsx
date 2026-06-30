/**
 * Agent 配置区块（嵌入统一面板内，不再自带外壳）
 */

import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import i18n from "../../../i18n";
import toast from "react-hot-toast";
import { AgentIcon } from "../../agent/AgentIcon";
import { AgentSectionSkeleton } from "../../skeletons";
import { agentConfigApi, roleApi, agentApi } from "../../../services/api";
import { useAuth } from "../../../hooks/useAuth";
import { Permission } from "../../../types";
import type { AgentConfig, Role, AgentInfo } from "../../../types";
import {
  resolveAgentDescription,
  resolveAgentDisplayName,
} from "../../agent/agentCatalog";
import { ConfigPanelErrorCallout } from "../ConfigPanelErrorCallout";
import { buildAgentCategoryContributions } from "../../../extensions";
import type { PluginRuntimeContributionStates } from "../../../extensions/coreContributions";
import { groupAgentsByPluginCategory } from "../AgentPanel/agentCategoryGroups";

import { GlobalAgentTab, RolesAgentTab } from "../AgentPanel/tabs";

type AgentTabType = "global" | "roles";

export function AgentSection({
  runtimePlugins,
}: {
  runtimePlugins?: PluginRuntimeContributionStates;
}) {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const canManageAgents = hasPermission(Permission.AGENT_ADMIN);
  const agentCategories = buildAgentCategoryContributions(runtimePlugins);
  const [activeTab, setActiveTab] = useState<AgentTabType>("global");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [globalAgents, setGlobalAgents] = useState<AgentConfig[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [roleAgentsMap, setRoleAgentsMap] = useState<Record<string, string[]>>(
    {},
  );
  const [availableAgents, setAvailableAgents] = useState<AgentInfo[]>([]);

  const loadData = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const [globalConfig, roleList, agentList] = await Promise.all([
        canManageAgents
          ? agentConfigApi.getCatalogConfig()
          : Promise.resolve(null),
        roleApi.list({ limit: 200 }),
        agentApi.list(),
      ]);

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

      if (globalConfig) {
        setGlobalAgents(globalConfig.agents || []);
      } else {
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

      setRoles(roleList.roles || []);

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

  if (isLoading) {
    return <AgentSectionSkeleton />;
  }

  return (
    <div className="animate-glass-enter px-4 py-5 sm:px-6 lg:px-7">
      {error && <ConfigPanelErrorCallout message={error} className="mb-4" />}

      {canManageAgents && (
        <div className="inline-grid grid-cols-2 rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg-subtle)] p-1 my-3">
          <button
            onClick={() => setActiveTab("global")}
            className={`flex items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-all duration-150 ${
              activeTab === "global"
                ? "bg-white text-stone-950 shadow-sm ring-1 ring-[var(--glass-border)] dark:bg-stone-800 dark:text-stone-50"
                : "text-stone-500 hover:bg-white/60 hover:text-stone-800 dark:text-stone-400 dark:hover:bg-stone-800/60 dark:hover:text-stone-100"
            }`}
          >
            {t("agentConfig.globalTab")}
          </button>
          <button
            onClick={() => setActiveTab("roles")}
            className={`flex items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-all duration-150 ${
              activeTab === "roles"
                ? "bg-white text-stone-950 shadow-sm ring-1 ring-[var(--glass-border)] dark:bg-stone-800 dark:text-stone-50"
                : "text-stone-500 hover:bg-white/60 hover:text-stone-800 dark:text-stone-400 dark:hover:bg-stone-800/60 dark:hover:text-stone-100"
            }`}
          >
            {t("agentConfig.rolesTab")}
          </button>
        </div>
      )}

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
        <div className="">
          <p className="text-sm text-theme-text-secondary px-1 leading-relaxed hidden sm:block">
            {t("agentConfig.availableAgents")}
          </p>
          <div className="glass-card divide-y divide-[var(--glass-border)] overflow-hidden rounded-xl">
            {groupAgentsByPluginCategory(availableAgents, agentCategories).flatMap((group) =>
              group.agents.map((agent, index) => {
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
                  className="flex items-center gap-3.5 px-4 py-3.5 transition-colors duration-150 hover:bg-[var(--glass-bg-hover)]"
                  style={{ animationDelay: `${index * 30}ms` }}
                >
                  <div className="flex size-10 flex-shrink-0 items-center justify-center overflow-hidden rounded-xl bg-[var(--glass-bg-subtle)] text-theme-text-secondary ring-1 ring-[var(--glass-border)]">
                    <AgentIcon icon={agent.icon || "Bot"} size={20} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <h4 className="truncate text-sm font-medium text-theme-text tracking-tight">
                      {displayName}
                    </h4>
                    <p className="mt-0.5 hidden truncate text-xs text-theme-text-secondary sm:block">
                      {displayDescription}
                    </p>
                  </div>
                </div>
              );
              }),
            )}
          </div>
        </div>
      )}
    </div>
  );
}
