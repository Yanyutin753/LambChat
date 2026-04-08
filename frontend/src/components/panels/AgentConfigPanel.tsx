/**
 * Agent 配置管理面板组件
 * 管理员配置全局 Agent 启用/禁用和角色分配
 * 支持响应式布局，适配手机端和桌面端
 */

import { useState, useEffect, useCallback } from "react";
import {
  Bot,
  Save,
  AlertCircle,
  RefreshCw,
  ChevronDown,
  Check,
  Settings,
  Sparkles,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { PanelHeader } from "../common/PanelHeader";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { agentConfigApi, roleApi, agentApi, settingsApi } from "../../services/api";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types";
import type { AgentConfig, Role, AgentInfo } from "../../types";

// Tab 类型
type TabType = "global" | "roles" | "models";

// 模型选项类型
interface ModelOption {
  value: string;
  label: string;
  description?: string;
}

/**
 * 全局 Agent 配置标签组件
 */
function GlobalAgentTab({
  agents,
  onUpdate,
  isLoading,
  isSaving,
}: {
  agents: AgentConfig[];
  onUpdate: (agents: AgentConfig[]) => void;
  isLoading: boolean;
  isSaving: boolean;
}) {
  const { t } = useTranslation();
  const [localAgents, setLocalAgents] = useState<AgentConfig[]>(agents);

  useEffect(() => {
    setLocalAgents(agents);
  }, [agents]);

  const toggleAgent = (agentId: string) => {
    setLocalAgents((prev) =>
      prev.map((a) => (a.id === agentId ? { ...a, enabled: !a.enabled } : a)),
    );
  };

  const handleSave = async () => {
    try {
      await onUpdate(localAgents);
    } catch (err) {
      console.error("Failed to save:", err);
    }
  };

  const hasChanges = JSON.stringify(localAgents) !== JSON.stringify(agents);

  if (isLoading) {
    return (
      <div className="flex h-40 items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-stone-500 dark:text-stone-400 px-1">
        {t("agentConfig.globalDescription")}
      </p>

      {/* Agent 列表 - 单列显示 */}
      <div className="grid gap-2 sm:gap-3">
        {localAgents.map((agent) => (
          <div
            key={agent.id}
            className="group flex items-center justify-between rounded-xl border border-stone-200/60 bg-white/80 p-3 sm:p-4 transition-all hover:border-stone-300 hover:shadow-sm dark:border-stone-700/60 dark:bg-stone-800/80 dark:hover:border-stone-600"
          >
            <div className="flex items-center gap-2.5 sm:gap-3 min-w-0 flex-1">
              <div className="flex h-10 w-10 sm:h-9 sm:w-9 flex-shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-stone-100 to-stone-200 dark:from-stone-700 dark:to-stone-800">
                <Bot size={18} className="text-stone-600 dark:text-stone-400" />
              </div>
              <div className="min-w-0 flex-1">
                <h4 className="text-sm font-medium text-stone-900 dark:text-stone-100 truncate">
                  {t(agent.name)}
                </h4>
                <div className="text-xs text-stone-500 dark:text-stone-400 truncate hidden sm:block">
                  {t(agent.description)}
                </div>
              </div>
            </div>

            {/* 开关 - 移动端增大触摸区域 */}
            <button
              onClick={() => toggleAgent(agent.id)}
              className={`relative h-7 w-12 sm:h-6 sm:w-11 flex-shrink-0 rounded-full transition-all duration-200 ${
                agent.enabled
                  ? "bg-gradient-to-r from-stone-500 to-stone-600 dark:from-stone-300 dark:to-stone-400"
                  : "bg-stone-200 dark:bg-stone-600"
              }`}
              aria-label={
                agent.enabled
                  ? `禁用 ${t(agent.name)}`
                  : `启用 ${t(agent.name)}`
              }
            >
              <span
                className={`absolute top-0.5 left-0.5 sm:left-0.5 h-6 w-6 sm:h-5 sm:w-5 rounded-full bg-white shadow-md transition-transform duration-200 ${
                  agent.enabled
                    ? "translate-x-5 sm:translate-x-5"
                    : "translate-x-0"
                }`}
              />
            </button>
          </div>
        ))}
      </div>

      {/* 保存按钮 */}
      {hasChanges && (
        <div className="flex justify-end pt-2">
          <button
            onClick={handleSave}
            disabled={isSaving}
            className="btn-primary flex items-center gap-2 px-4 py-2.5 sm:px-4 sm:py-2 text-sm sm:text-base"
          >
            {isSaving ? (
              <>
                <LoadingSpinner size="sm" />
                {t("common.saving")}
              </>
            ) : (
              <>
                <Save size={16} />
                {t("common.save")}
              </>
            )}
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * 角色 Agent 分配标签组件
 */
function RolesAgentTab({
  roles,
  roleAgentsMap,
  availableAgents,
  onUpdate,
  isLoading,
}: {
  roles: Role[];
  roleAgentsMap: Record<string, string[]>;
  availableAgents: AgentInfo[];
  onUpdate: (roleId: string, agentIds: string[]) => void;
  isLoading: boolean;
}) {
  const { t } = useTranslation();
  const [selectedRole, setSelectedRole] = useState<string | null>(
    roles.length > 0 ? roles[0].id : null,
  );
  const [localRoleAgents, setLocalRoleAgents] =
    useState<Record<string, string[]>>(roleAgentsMap);
  const [roleDropdownOpen, setRoleDropdownOpen] = useState(false);

  useEffect(() => {
    setLocalRoleAgents(roleAgentsMap);
  }, [roleAgentsMap]);

  if (isLoading) {
    return (
      <div className="flex h-40 items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  const currentRoleAgents = selectedRole
    ? localRoleAgents[selectedRole] || []
    : [];

  const toggleAgent = (agentId: string) => {
    if (!selectedRole) return;
    setLocalRoleAgents((prev) => {
      const current = prev[selectedRole] || [];
      if (current.includes(agentId)) {
        return {
          ...prev,
          [selectedRole]: current.filter((id) => id !== agentId),
        };
      }
      return { ...prev, [selectedRole]: [...current, agentId] };
    });
  };

  const handleSave = async () => {
    if (!selectedRole) return;
    try {
      await onUpdate(selectedRole, localRoleAgents[selectedRole] || []);
    } catch (err) {
      console.error("Failed to save role agents:", err);
    }
  };

  const selectedRoleData = roles.find((r) => r.id === selectedRole);
  const hasChanges = selectedRole
    ? JSON.stringify(localRoleAgents[selectedRole]) !==
      JSON.stringify(roleAgentsMap[selectedRole])
    : false;

  if (isLoading) {
    return (
      <div className="flex h-40 items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-stone-500 dark:text-stone-400 px-1">
        {t("agentConfig.rolesDescription")}
      </p>

      {/* 角色选择器 - 手机端使用下拉菜单，桌面端使用标签 */}
      <div className="block sm:hidden">
        {/* 手机端下拉选择 */}
        <div className="relative">
          <button
            onClick={() => setRoleDropdownOpen(!roleDropdownOpen)}
            className="flex w-full items-center justify-between rounded-lg border border-stone-300 bg-white px-4 py-3 text-sm font-medium text-stone-900 dark:border-stone-600 dark:bg-stone-800 dark:text-stone-100"
          >
            <span className="flex items-center gap-2">
              <Settings size={16} className="text-stone-500" />
              {selectedRoleData?.name || t("agentConfig.selectRole")}
            </span>
            <ChevronDown
              size={18}
              className={`text-stone-500 transition-transform ${
                roleDropdownOpen ? "rotate-180" : ""
              }`}
            />
          </button>

          {roleDropdownOpen && (
            <div className="absolute z-10 mt-1 w-full rounded-lg border border-stone-200 bg-white shadow-lg dark:border-stone-700 dark:bg-stone-800">
              {roles.map((role) => (
                <button
                  key={role.id}
                  onClick={() => {
                    setSelectedRole(role.id);
                    setRoleDropdownOpen(false);
                  }}
                  className={`flex w-full items-center justify-between px-4 py-3 text-sm transition-colors first:rounded-t-lg last:rounded-b-lg ${
                    selectedRole === role.id
                      ? "bg-stone-100 text-stone-900 dark:bg-stone-700 dark:text-stone-100"
                      : "text-stone-700 hover:bg-stone-50 dark:text-stone-300 dark:hover:bg-stone-700/50"
                  }`}
                >
                  <span>{role.name}</span>
                  {selectedRole === role.id && (
                    <Check
                      size={16}
                      className="text-stone-600 dark:text-stone-400"
                    />
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 桌面端标签选择 */}
      <div className="hidden sm:flex gap-1.5 overflow-x-auto pb-2">
        {roles.map((role) => (
          <button
            key={role.id}
            onClick={() => setSelectedRole(role.id)}
            className={`flex-shrink-0 rounded-lg px-4 py-2 text-sm font-medium transition-all ${
              selectedRole === role.id
                ? "bg-gradient-to-r from-stone-500 to-stone-600 text-white shadow-sm dark:from-stone-400 dark:to-stone-500 dark:text-stone-900"
                : "bg-stone-100 text-stone-600 hover:bg-stone-200 dark:bg-stone-800 dark:text-stone-400 dark:hover:bg-stone-700"
            }`}
          >
            {role.name}
          </button>
        ))}
      </div>

      {selectedRole && (
        <>
          {/* 可用 Agents 选择 */}
          <div className="rounded-xl border border-stone-200/60 bg-stone-50/80 p-4 dark:border-stone-700/60 dark:bg-stone-900/50">
            <h4 className="mb-3 text-sm font-medium text-stone-900 dark:text-stone-100">
              {t("agentConfig.selectAgentsForRole", {
                roleName: selectedRoleData?.name,
              })}
            </h4>
            <div className="grid gap-2 space-y-1 sm:space-y-2">
              {availableAgents.map((agent) => (
                <label
                  key={agent.id}
                  className={`flex cursor-pointer items-center gap-3 rounded-lg bg-white p-3 transition-all dark:bg-stone-800 ${
                    currentRoleAgents.includes(agent.id)
                      ? "ring-2 ring-stone-500/50 dark:ring-stone-400/50 shadow-sm"
                      : "hover:bg-stone-50 dark:hover:bg-stone-700/50"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={currentRoleAgents.includes(agent.id)}
                    onChange={() => toggleAgent(agent.id)}
                    className="h-5 w-5"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-stone-900 dark:text-stone-100 truncate">
                      {t(agent.name)}
                    </div>
                    <div className="text-xs text-stone-500 dark:text-stone-400 truncate hidden sm:block">
                      {t(agent.description)}
                    </div>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {/* 保存按钮 */}
          {hasChanges && (
            <div className="flex justify-end pt-2">
              <button
                onClick={handleSave}
                className="btn-primary flex items-center gap-2 px-4 py-2.5 text-sm"
              >
                <Save size={16} />
                {t("common.save")}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

/**
 * 角色 Model 分配标签组件
 */
function RolesModelTab({
  roles,
  roleModelsMap,
  availableModels,
  onUpdate,
  isLoading,
}: {
  roles: Role[];
  roleModelsMap: Record<string, string[]>;
  availableModels: ModelOption[];
  onUpdate: (roleId: string, modelValues: string[]) => void;
  isLoading: boolean;
}) {
  const { t } = useTranslation();
  const [selectedRole, setSelectedRole] = useState<string | null>(
    roles.length > 0 ? roles[0].id : null,
  );
  const [localRoleModels, setLocalRoleModels] =
    useState<Record<string, string[]>>(roleModelsMap);
  const [roleDropdownOpen, setRoleDropdownOpen] = useState(false);

  useEffect(() => {
    setLocalRoleModels(roleModelsMap);
  }, [roleModelsMap]);

  if (isLoading) {
    return (
      <div className="flex h-40 items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  const currentRoleModels = selectedRole
    ? localRoleModels[selectedRole] || []
    : [];

  const toggleModel = (modelValue: string) => {
    if (!selectedRole) return;
    setLocalRoleModels((prev) => {
      const current = prev[selectedRole] || [];
      if (current.includes(modelValue)) {
        return {
          ...prev,
          [selectedRole]: current.filter((v) => v !== modelValue),
        };
      }
      return { ...prev, [selectedRole]: [...current, modelValue] };
    });
  };

  const handleSave = async () => {
    if (!selectedRole) return;
    try {
      await onUpdate(selectedRole, localRoleModels[selectedRole] || []);
    } catch (err) {
      console.error("Failed to save role models:", err);
    }
  };

  const selectedRoleData = roles.find((r) => r.id === selectedRole);
  const hasChanges = selectedRole
    ? JSON.stringify(localRoleModels[selectedRole]) !==
      JSON.stringify(roleModelsMap[selectedRole])
    : false;

  if (availableModels.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-stone-500 dark:text-stone-400">
        <Sparkles size={32} className="mb-3 opacity-40" />
        <p className="text-sm">{t("agentConfig.noModelsConfigured")}</p>
        <p className="text-xs mt-1 opacity-70">{t("agentConfig.noModelsConfiguredHint")}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-stone-500 dark:text-stone-400 px-1">
        {t("agentConfig.modelsDescription")}
      </p>

      {/* 角色选择器 - 手机端使用下拉菜单，桌面端使用标签 */}
      <div className="block sm:hidden">
        <div className="relative">
          <button
            onClick={() => setRoleDropdownOpen(!roleDropdownOpen)}
            className="flex w-full items-center justify-between rounded-lg border border-stone-300 bg-white px-4 py-3 text-sm font-medium text-stone-900 dark:border-stone-600 dark:bg-stone-800 dark:text-stone-100"
          >
            <span className="flex items-center gap-2">
              <Settings size={16} className="text-stone-500" />
              {selectedRoleData?.name || t("agentConfig.selectRole")}
            </span>
            <ChevronDown
              size={18}
              className={`text-stone-500 transition-transform ${
                roleDropdownOpen ? "rotate-180" : ""
              }`}
            />
          </button>

          {roleDropdownOpen && (
            <div className="absolute z-10 mt-1 w-full rounded-lg border border-stone-200 bg-white shadow-lg dark:border-stone-700 dark:bg-stone-800">
              {roles.map((role) => (
                <button
                  key={role.id}
                  onClick={() => {
                    setSelectedRole(role.id);
                    setRoleDropdownOpen(false);
                  }}
                  className={`flex w-full items-center justify-between px-4 py-3 text-sm transition-colors first:rounded-t-lg last:rounded-b-lg ${
                    selectedRole === role.id
                      ? "bg-stone-100 text-stone-900 dark:bg-stone-700 dark:text-stone-100"
                      : "text-stone-700 hover:bg-stone-50 dark:text-stone-300 dark:hover:bg-stone-700/50"
                  }`}
                >
                  <span>{role.name}</span>
                  {selectedRole === role.id && (
                    <Check
                      size={16}
                      className="text-stone-600 dark:text-stone-400"
                    />
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 桌面端标签选择 */}
      <div className="hidden sm:flex gap-1.5 overflow-x-auto pb-2">
        {roles.map((role) => (
          <button
            key={role.id}
            onClick={() => setSelectedRole(role.id)}
            className={`flex-shrink-0 rounded-lg px-4 py-2 text-sm font-medium transition-all ${
              selectedRole === role.id
                ? "bg-gradient-to-r from-stone-500 to-stone-600 text-white shadow-sm dark:from-stone-400 dark:to-stone-500 dark:text-stone-900"
                : "bg-stone-100 text-stone-600 hover:bg-stone-200 dark:bg-stone-800 dark:text-stone-400 dark:hover:bg-stone-700"
            }`}
          >
            {role.name}
          </button>
        ))}
      </div>

      {selectedRole && (
        <>
          {/* 可用 Models 选择 */}
          <div className="rounded-xl border border-stone-200/60 bg-stone-50/80 p-4 dark:border-stone-700/60 dark:bg-stone-900/50">
            <h4 className="mb-3 text-sm font-medium text-stone-900 dark:text-stone-100">
              {t("agentConfig.selectModelsForRole", {
                roleName: selectedRoleData?.name,
              })}
            </h4>
            <div className="grid gap-2 space-y-1 sm:space-y-2">
              {availableModels.map((model) => (
                <label
                  key={model.value}
                  className={`flex cursor-pointer items-center gap-3 rounded-lg bg-white p-3 transition-all dark:bg-stone-800 ${
                    currentRoleModels.includes(model.value)
                      ? "ring-2 ring-stone-500/50 dark:ring-stone-400/50 shadow-sm"
                      : "hover:bg-stone-50 dark:hover:bg-stone-700/50"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={currentRoleModels.includes(model.value)}
                    onChange={() => toggleModel(model.value)}
                    className="h-5 w-5"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-stone-900 dark:text-stone-100 truncate">
                      {model.label}
                    </div>
                    {model.description && (
                      <div className="text-xs text-stone-500 dark:text-stone-400 truncate hidden sm:block">
                        {model.description}
                      </div>
                    )}
                  </div>
                </label>
              ))}
            </div>
          </div>

          {/* 保存按钮 */}
          {hasChanges && (
            <div className="flex justify-end pt-2">
              <button
                onClick={handleSave}
                className="btn-primary flex items-center gap-2 px-4 py-2.5 text-sm"
              >
                <Save size={16} />
                {t("common.save")}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

/**
 * Agent 配置面板主组件
 */
export function AgentConfigPanel() {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const canManageAgents = hasPermission(Permission.AGENT_ADMIN);
  const canManageModels = hasPermission(Permission.MODEL_ADMIN);
  const [activeTab, setActiveTab] = useState<TabType>(
    canManageAgents ? "global" : "models",
  );
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 数据状态
  const [globalAgents, setGlobalAgents] = useState<AgentConfig[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [roleAgentsMap, setRoleAgentsMap] = useState<Record<string, string[]>>(
    {},
  );
  const [roleModelsMap, setRoleModelsMap] = useState<Record<string, string[]>>(
    {},
  );
  const [availableAgents, setAvailableAgents] = useState<AgentInfo[]>([]);
  const [availableModels, setAvailableModels] = useState<ModelOption[]>([]);

  const showTabBar = canManageAgents || canManageModels;

  // 加载数据
  const loadData = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      // 并行加载所有数据
      const [globalConfig, roleList, agentList, settingsData] = await Promise.all([
        canManageAgents ? agentConfigApi.getGlobalConfig() : Promise.resolve(null),
        roleApi.list(),
        agentApi.list(),
        (canManageAgents || canManageModels) ? settingsApi.list() : Promise.resolve(null),
      ]);

      // 加载全局可用模型列表
      if (settingsData?.settings) {
        const allSettings = Object.values(settingsData.settings).flat();
        const llmModels = allSettings.find(
          (s: { key: string }) => s.key === "LLM_AVAILABLE_MODELS",
        );
        if (llmModels?.value && Array.isArray(llmModels.value) && llmModels.value.length > 0) {
          setAvailableModels(llmModels.value as ModelOption[]);
        }
      }

      // 管理员使用全局配置的全部 agent（用于角色分配），非管理员使用过滤后的列表
      setAvailableAgents(
        canManageAgents && globalConfig
          ? globalConfig.agents.map((a) => ({
              id: a.id,
              name: a.name,
              description: a.description,
              version: "",
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
          })),
        );
      }

      // 设置角色列表
      setRoles(roleList || []);

      // 加载角色-agents 映射
      if (canManageAgents) {
        const roleAgentPromises = (roleList || []).map(async (role) => {
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

      // 加载角色-models 映射
      if (canManageModels) {
        const roleModelPromises = (roleList || []).map(async (role) => {
          try {
            const assignment = await agentConfigApi.getRoleModels(role.id);
            return { roleId: role.id, models: assignment.allowed_models };
          } catch {
            return { roleId: role.id, models: [] };
          }
        });
        const roleModelResults = await Promise.all(roleModelPromises);
        const modelMap: Record<string, string[]> = {};
        roleModelResults.forEach(({ roleId, models }) => {
          modelMap[roleId] = models;
        });
        setRoleModelsMap(modelMap);
      }
    } catch (err) {
      const errorMsg = (err as Error).message || t("agentConfig.loadFailed");
      setError(errorMsg);
      toast.error(errorMsg);
    } finally {
      setIsLoading(false);
    }
  }, [canManageAgents, canManageModels, t]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // 更新全局配置
  const handleUpdateGlobalConfig = async (agents: AgentConfig[]) => {
    if (!canManageAgents) return;
    setIsSaving(true);
    try {
      await agentConfigApi.updateGlobalConfig(agents);
      setGlobalAgents(agents);
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

  // 更新角色模型配置
  const handleUpdateRoleModels = async (roleId: string, modelValues: string[]) => {
    if (!canManageModels) return;
    try {
      await agentConfigApi.updateRoleModels(roleId, modelValues);
      setRoleModelsMap((prev) => ({ ...prev, [roleId]: modelValues }));
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
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col min-h-0">
      {/* 头部 */}
      <PanelHeader
        title={t("agentConfig.title")}
        icon={<Bot size={20} className="text-stone-600 dark:text-stone-400" />}
        actions={
          <button
            onClick={handleRefresh}
            className="btn-secondary flex items-center gap-2 px-3 py-2 sm:px-3 sm:py-1.5"
            aria-label={t("common.refresh")}
          >
            <RefreshCw size={16} />
            <span className="hidden sm:inline text-sm">
              {t("common.refresh")}
            </span>
          </button>
        }
      />

      {/* 错误提示 */}
      {error && (
        <div className="mx-4 mt-4 flex items-center gap-2 rounded-xl bg-red-50 p-3 text-sm text-red-600 dark:bg-red-900/30 dark:text-red-400 sm:mx-6">
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      {/* Tab 切换 - 移动端增大触摸区域 */}
      {showTabBar && (
        <div className="flex border-b border-stone-200 dark:border-stone-800">
          {canManageAgents && (
            <>
              <button
                onClick={() => setActiveTab("global")}
                className={`flex-1 px-3 py-4 sm:px-4 sm:py-3 text-center text-sm font-medium transition-all relative ${
                  activeTab === "global"
                    ? "text-stone-900 dark:text-stone-100"
                    : "text-stone-500 hover:text-stone-700 dark:text-stone-400 dark:hover:text-stone-200"
                }`}
              >
                {activeTab === "global" && (
                  <span className="absolute bottom-0 left-2 right-2 h-0.5 rounded-full bg-gradient-to-r from-stone-500 to-stone-600 dark:from-stone-400 dark:to-stone-500" />
                )}
                {t("agentConfig.globalTab")}
              </button>
              <button
                onClick={() => setActiveTab("roles")}
                className={`flex-1 px-3 py-4 sm:px-4 sm:py-3 text-center text-sm font-medium transition-all relative ${
                  activeTab === "roles"
                    ? "text-stone-900 dark:text-stone-100"
                    : "text-stone-500 hover:text-stone-700 dark:text-stone-400 dark:hover:text-stone-200"
                }`}
              >
                {activeTab === "roles" && (
                  <span className="absolute bottom-0 left-2 right-2 h-0.5 rounded-full bg-gradient-to-r from-stone-500 to-stone-600 dark:from-stone-400 dark:to-stone-500" />
                )}
                {t("agentConfig.rolesTab")}
              </button>
            </>
          )}
          {canManageModels && (
            <button
              onClick={() => setActiveTab("models")}
              className={`flex-1 px-3 py-4 sm:px-4 sm:py-3 text-center text-sm font-medium transition-all relative ${
                activeTab === "models"
                  ? "text-stone-900 dark:text-stone-100"
                  : "text-stone-500 hover:text-stone-700 dark:text-stone-400 dark:hover:text-stone-200"
              }`}
            >
              {activeTab === "models" && (
                <span className="absolute bottom-0 left-2 right-2 h-0.5 rounded-full bg-gradient-to-r from-stone-500 to-stone-600 dark:from-stone-400 dark:to-stone-500" />
              )}
              {t("agentConfig.modelsTab")}
            </button>
          )}
        </div>
      )}

      {/* 内容 */}
      <div className="flex-1 overflow-y-auto px-3 py-4 sm:px-6 sm:py-5">
        {showTabBar && activeTab === "models" && canManageModels ? (
          <RolesModelTab
            roles={roles}
            roleModelsMap={roleModelsMap}
            availableModels={availableModels}
            onUpdate={handleUpdateRoleModels}
            isLoading={isLoading}
          />
        ) : canManageAgents ? (
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
          <div className="space-y-4">
            <p className="text-sm text-stone-500 dark:text-stone-400 px-1">
              {t("agentConfig.availableAgents")}
            </p>
            <div className="grid gap-2">
              {availableAgents.map((agent) => (
                <div
                  key={agent.id}
                  className="flex items-center gap-3 rounded-xl border border-stone-200/60 bg-white/80 p-3 sm:p-4 transition-all hover:border-stone-300 hover:shadow-sm dark:border-stone-700/60 dark:bg-stone-800/80 dark:hover:border-stone-600"
                >
                  <div className="flex h-10 w-10 sm:h-9 sm:w-9 flex-shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-stone-100 to-stone-200 dark:from-stone-700 dark:to-stone-800">
                    <Bot
                      size={18}
                      className="text-stone-600 dark:text-stone-400"
                    />
                  </div>
                  <div className="min-w-0 flex-1">
                    <h4 className="font-medium text-stone-900 dark:text-stone-100 truncate">
                      {t(agent.name)}
                    </h4>
                    <p className="text-sm text-stone-500 dark:text-stone-400 truncate sm:hidden">
                      {t(agent.description)}
                    </p>
                    <p className="text-sm text-stone-500 dark:text-stone-400 truncate hidden sm:block">
                      {t(agent.description)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default AgentConfigPanel;
