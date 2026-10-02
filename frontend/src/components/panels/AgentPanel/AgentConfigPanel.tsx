/**
 * Agent 配置管理面板组件
 * 管理员配置全局 Agent 启用/禁用和角色分配
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import i18n from "../../../i18n";
import toast from "react-hot-toast";
import { Button } from "../../common";
import { PanelHeader } from "../../common/PanelHeader";
import { AgentIcon } from "../../agent/AgentIcon";
import { AgentPanelSkeleton } from "../../skeletons";
import { agentConfigApi, roleApi, agentApi } from "../../../services/api";
import { useAuth } from "../../../hooks/useAuth";
import { Permission } from "../../../types";
import type { AgentConfig, Role, AgentInfo } from "../../../types";
import {
  resolveAgentDescription,
  resolveAgentDisplayName,
} from "../../agent/agentCatalog";
import { ConfigPanelErrorCallout } from "../ConfigPanelErrorCallout";

import { GlobalAgentTab, RolesAgentTab } from "./tabs";

type AgentTabType = "global" | "roles";

/**
 * Agent 配置面板主组件
 */
export function AgentConfigPanel() {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const canManageAgents = hasPermission(Permission.AGENT_ADMIN);
  const [activeTab, setActiveTab] = useState<AgentTabType>("global");
  const [isLoading, setIsLoading] = useState(true);
  const [hasLoaded, setHasLoaded] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const loadGeneration = useRef(0);
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
    const generation = ++loadGeneration.current;
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

      if (generation !== loadGeneration.current) return;

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
            labels: a.labels,
          })),
        );
      }

      // 设置角色列表
      setRoles(roleList.roles || []);

      // 加载角色-agents 映射
      if (canManageAgents) {
        const roleAgentPromises = (roleList.roles || []).map(async (role) => {
          const assignment = await agentConfigApi.getRoleAgents(role.id);
          return { roleId: role.id, agents: assignment.allowed_agents };
        });
        const roleAgentResults = await Promise.all(roleAgentPromises);
        if (generation !== loadGeneration.current) return;
        const map: Record<string, string[]> = {};
        roleAgentResults.forEach(({ roleId, agents }) => {
          map[roleId] = agents;
        });
        setRoleAgentsMap(map);
      }
    } catch (err) {
      if (generation !== loadGeneration.current) return;
      const errorMsg =
        (err as Error).message || i18n.t("agentConfig.loadFailed");
      setError(errorMsg);
    } finally {
      if (generation === loadGeneration.current) {
        setIsLoading(false);
        setHasLoaded(true);
      }
    }
  }, [canManageAgents]);

  useEffect(() => {
    const requests = loadGeneration;
    loadData();
    return () => {
      requests.current++;
    };
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
    await agentConfigApi.updateRoleAgents(roleId, agentIds);
    setRoleAgentsMap((prev) => ({ ...prev, [roleId]: agentIds }));
    toast.success(t("agentConfig.saveSuccess"));
  };

  // 刷新数据
  const handleRefresh = () => {
    loadData();
  };

  if (isLoading && !hasLoaded) {
    return <AgentPanelSkeleton />;
  }

  return (
    <div
      ref={rootRef}
      tabIndex={-1}
      aria-busy={isLoading}
      className="glass-shell flex h-full flex-col min-h-0 focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)]"
    >
      {/* 头部 */}
      <PanelHeader
        title={t("agentConfig.title")}
        subtitle={t("agentConfig.subtitle")}
        illustration="panel-agents"
        actions={
          <Button
            onClick={handleRefresh}
            leftIcon={<RefreshCw size={16} />}
            aria-label={t("common.refresh")}
          >
            <span className="hidden sm:inline text-14">
              {t("common.refresh")}
            </span>
          </Button>
        }
      />

      {error ? (
        <div className="panel-body panel-stack">
          <ConfigPanelErrorCallout message={error} />
          <Button
            onClick={() => {
              rootRef.current?.focus({ preventScroll: true });
              void loadData();
            }}
          >
            {t("common.retry")}
          </Button>
        </div>
      ) : isLoading ? (
        <AgentPanelSkeleton />
      ) : (
        <>
          {/* Tab 切换 */}
          {canManageAgents && (
            <div className="flex glass-divider px-2">
              <button
                onClick={() => setActiveTab("global")}
                className={`px-4 py-3.5 text-14 font-medium transition-all relative ${
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
                className={`px-4 py-3.5 text-14 font-medium transition-all relative ${
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
          <div className="panel-body flex-1 overflow-y-auto">
            {canManageAgents ? (
              activeTab === "global" ? (
                <GlobalAgentTab
                  agents={globalAgents}
                  onUpdate={handleUpdateGlobalConfig}
                  isLoading={isLoading}
                  isSaving={isSaving}
                />
              ) : (
                <RolesAgentTab
                  roles={roles}
                  roleAgentsMap={roleAgentsMap}
                  availableAgents={availableAgents}
                  onUpdate={handleUpdateRoleAgents}
                  isLoading={isLoading}
                />
              )
            ) : (
              // 非管理员只显示可用 agents
              <div className="space-y-5">
                <p className="text-14 text-stone-500 dark:text-stone-400 px-1 leading-relaxed">
                  {t("agentConfig.availableAgents")}
                </p>
                <div className="grid gap-3">
                  {availableAgents.map((agent) => {
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
                          <h4 className="text-14 font-semibold text-stone-900 dark:text-stone-100 truncate tracking-tight font-serif">
                            {displayName}
                          </h4>
                          <p className="text-12 text-stone-500 dark:text-stone-400 truncate mt-0.5 hidden sm:block">
                            {displayDescription}
                          </p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default AgentConfigPanel;
