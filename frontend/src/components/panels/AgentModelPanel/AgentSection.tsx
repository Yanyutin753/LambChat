/**
 * Agent 配置区块（嵌入统一面板内，不再自带外壳）
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { useTranslation } from "react-i18next";
import i18n from "../../../i18n";
import toast from "react-hot-toast";
import { Button, EmptyState } from "../../common";
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

import { GlobalAgentTab, RolesAgentTab } from "../AgentPanel/tabs";

type AgentTabType = "global" | "roles";

export function AgentSection() {
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

  const [globalAgents, setGlobalAgents] = useState<AgentConfig[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [roleAgentsMap, setRoleAgentsMap] = useState<Record<string, string[]>>(
    {},
  );
  const [availableAgents, setAvailableAgents] = useState<AgentInfo[]>([]);

  const loadData = useCallback(async () => {
    const generation = ++loadGeneration.current;
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

      if (generation !== loadGeneration.current) return;
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
            labels: a.labels,
          })),
        );
      }

      setRoles(roleList.roles || []);

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

  const handleUpdateRoleAgents = async (roleId: string, agentIds: string[]) => {
    if (!canManageAgents) return;
    await agentConfigApi.updateRoleAgents(roleId, agentIds);
    setRoleAgentsMap((prev) => ({ ...prev, [roleId]: agentIds }));
    toast.success(t("agentConfig.saveSuccess"));
  };

  if (isLoading && !hasLoaded) {
    return <AgentSectionSkeleton />;
  }

  return (
    <div
      ref={rootRef}
      tabIndex={-1}
      aria-busy={isLoading}
      className={`${isLoading ? "" : "panel-body panel-stack"} focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)]`}
    >
      {error ? (
        <>
          <ConfigPanelErrorCallout message={error} />
          <Button
            onClick={() => {
              rootRef.current?.focus({ preventScroll: true });
              void loadData();
            }}
          >
            {t("common.retry")}
          </Button>
        </>
      ) : isLoading ? (
        <AgentSectionSkeleton />
      ) : (
        <>
          {canManageAgents && (
            <div className="inline-grid grid-cols-2 rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg-subtle)] p-1 self-start max-w-full font-serif">
              <button
                type="button"
                aria-pressed={activeTab === "global"}
                onClick={() => setActiveTab("global")}
                className={`flex items-center justify-center gap-2 rounded-md px-3 py-2 text-14 font-medium min-h-11 transition-colors duration-150 motion-reduce:transition-none focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)] ${
                  activeTab === "global"
                    ? "bg-white text-stone-950 shadow-sm ring-1 ring-[var(--glass-border)] dark:bg-stone-800 dark:text-stone-50"
                    : "text-stone-500 hover:bg-white/60 hover:text-stone-800 dark:text-stone-400 dark:hover:bg-stone-800/60 dark:hover:text-stone-100"
                }`}
              >
                {t("agentConfig.globalTab")}
              </button>
              <button
                type="button"
                aria-pressed={activeTab === "roles"}
                onClick={() => setActiveTab("roles")}
                className={`flex items-center justify-center gap-2 rounded-md px-3 py-2 text-14 font-medium min-h-11 transition-colors duration-150 motion-reduce:transition-none focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)] ${
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
            <>
              <div hidden={activeTab !== "global"}>
                <GlobalAgentTab
                  agents={globalAgents}
                  onUpdate={handleUpdateGlobalConfig}
                  isLoading={isLoading}
                  isSaving={isSaving}
                />
              </div>
              <div hidden={activeTab !== "roles"}>
                <RolesAgentTab
                  roles={roles}
                  roleAgentsMap={roleAgentsMap}
                  availableAgents={availableAgents}
                  onUpdate={handleUpdateRoleAgents}
                  isLoading={isLoading}
                />
              </div>
            </>
          ) : (
            <div className="">
              {availableAgents.length === 0 && (
                <EmptyState
                  illustration="panel-agents"
                  title={t("agentConfig.noAvailableAgents")}
                />
              )}
              <p className="text-14 text-theme-text-secondary px-1 leading-relaxed hidden sm:block">
                {t("agentConfig.availableAgents")}
              </p>
              <div className="glass-card divide-y divide-[var(--glass-border)] overflow-hidden rounded-xl">
                {availableAgents.map((agent, index) => {
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
                        <h4 className="truncate text-14 font-medium font-serif text-theme-text tracking-tight">
                          {displayName}
                        </h4>
                        <p className="mt-0.5 hidden truncate text-12 text-theme-text-secondary sm:block">
                          {displayDescription}
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
