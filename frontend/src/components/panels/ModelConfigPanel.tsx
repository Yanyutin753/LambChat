/**
 * Model 配置管理面板组件
 * 管理员配置 Provider 凭证、全局 Model 启用/禁用和角色分配
 * 支持响应式布局，适配手机端和桌面端
 */

import { useState, useEffect, useCallback } from "react";
import {
  Cpu,
  Save,
  AlertCircle,
  RefreshCw,
  ChevronDown,
  Check,
  Settings,
  Eye,
  EyeOff,
  Server,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { PanelHeader } from "../common/PanelHeader";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { modelConfigApi, roleApi } from "../../services/api";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types";
import type { ModelConfig, ProviderConfig, Role } from "../../types";

// Tab 类型
type TabType = "providers" | "global" | "roles";

// ============================================
// Provider 配置标签
// ============================================

function ProvidersTab({
  providers,
  onUpdate,
  isLoading,
  isSaving,
}: {
  providers: ProviderConfig[];
  onUpdate: (providers: ProviderConfig[]) => void;
  isLoading: boolean;
  isSaving: boolean;
}) {
  const { t } = useTranslation();
  const [localProviders, setLocalProviders] = useState<ProviderConfig[]>(providers);
  const [showApiKeys, setShowApiKeys] = useState<Record<string, boolean>>({});

  useEffect(() => {
    setLocalProviders(providers);
  }, [providers]);

  const updateProvider = (name: string, field: keyof ProviderConfig, value: string | boolean | null) => {
    setLocalProviders((prev) =>
      prev.map((p) => (p.name === name ? { ...p, [field]: value } : p)),
    );
  };

  const handleSave = async () => {
    try {
      await onUpdate(localProviders);
    } catch (err) {
      console.error("Failed to save providers:", err);
    }
  };

  const hasChanges = JSON.stringify(localProviders) !== JSON.stringify(providers);

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
        {t("modelConfig.providersDescription")}
      </p>

      <div className="grid gap-3">
        {localProviders.map((provider) => (
          <div
            key={provider.name}
            className="rounded-xl border border-stone-200/60 bg-white/80 p-4 dark:border-stone-700/60 dark:bg-stone-800/80"
          >
            {/* Provider Header */}
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2.5">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-blue-100 to-blue-200 dark:from-blue-900 dark:to-blue-800">
                  <Server size={16} className="text-blue-600 dark:text-blue-400" />
                </div>
                <div>
                  <h4 className="text-sm font-medium text-stone-900 dark:text-stone-100">
                    {provider.display_name || provider.name}
                  </h4>
                  <span className="text-xs text-stone-400">{provider.name}</span>
                </div>
              </div>
              {/* 启用开关 */}
              <button
                onClick={() => updateProvider(provider.name, "enabled", !provider.enabled)}
                className={`relative h-6 w-11 flex-shrink-0 rounded-full transition-all duration-200 ${
                  provider.enabled
                    ? "bg-gradient-to-r from-blue-500 to-blue-600"
                    : "bg-stone-200 dark:bg-stone-600"
                }`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow-md transition-transform duration-200 ${
                    provider.enabled ? "translate-x-5" : "translate-x-0"
                  }`}
                />
              </button>
            </div>

            {/* API Base URL */}
            <div className="mb-2">
              <label className="block text-xs font-medium text-stone-500 dark:text-stone-400 mb-1">
                API Base URL
              </label>
              <input
                type="text"
                value={provider.api_base || ""}
                onChange={(e) => updateProvider(provider.name, "api_base", e.target.value || null)}
                placeholder="https://api.openai.com"
                className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm text-stone-900 placeholder:text-stone-400 focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400 dark:border-stone-600 dark:bg-stone-700 dark:text-stone-100 dark:placeholder:text-stone-500"
              />
            </div>

            {/* API Key */}
            <div>
              <label className="block text-xs font-medium text-stone-500 dark:text-stone-400 mb-1">
                API Key
              </label>
              <div className="relative">
                <input
                  type={showApiKeys[provider.name] ? "text" : "password"}
                  value={provider.api_key || ""}
                  onChange={(e) => updateProvider(provider.name, "api_key", e.target.value || null)}
                  placeholder="sk-..."
                  className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 pr-9 text-sm text-stone-900 placeholder:text-stone-400 focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400 dark:border-stone-600 dark:bg-stone-700 dark:text-stone-100 dark:placeholder:text-stone-500"
                />
                <button
                  type="button"
                  onClick={() =>
                    setShowApiKeys((prev) => ({
                      ...prev,
                      [provider.name]: !prev[provider.name],
                    }))
                  }
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-stone-400 hover:text-stone-600 dark:hover:text-stone-300"
                >
                  {showApiKeys[provider.name] ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {localProviders.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12 text-stone-500 dark:text-stone-400">
          <Server size={40} className="mb-3 opacity-30" />
          <p className="text-sm">{t("modelConfig.noModels")}</p>
        </div>
      )}

      {/* 保存按钮 */}
      {hasChanges && (
        <div className="flex justify-end pt-2">
          <button
            onClick={handleSave}
            disabled={isSaving}
            className="btn-primary flex items-center gap-2 px-4 py-2.5 text-sm"
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

// ============================================
// 全局 Model 配置标签
// ============================================

/**
 * 全局 Model 配置标签组件
 */
function GlobalModelTab({
  models,
  onUpdate,
  isLoading,
  isSaving,
}: {
  models: ModelConfig[];
  onUpdate: (models: ModelConfig[]) => void;
  isLoading: boolean;
  isSaving: boolean;
}) {
  const { t } = useTranslation();
  const [localModels, setLocalModels] = useState<ModelConfig[]>(models);
  const [expandedModel, setExpandedModel] = useState<string | null>(null);
  const [showApiKeys, setShowApiKeys] = useState<Record<string, boolean>>({});

  useEffect(() => {
    setLocalModels(models);
  }, [models]);

  const toggleModel = (modelId: string) => {
    setLocalModels((prev) =>
      prev.map((m) =>
        m.id === modelId ? { ...m, enabled: !m.enabled } : m,
      ),
    );
  };

  const updateModelField = (modelId: string, field: keyof ModelConfig, value: string | boolean | null) => {
    setLocalModels((prev) =>
      prev.map((m) => (m.id === modelId ? { ...m, [field]: value } : m)),
    );
  };

  const handleSave = async () => {
    try {
      await onUpdate(localModels);
    } catch (err) {
      console.error("Failed to save:", err);
    }
  };

  const hasChanges = JSON.stringify(localModels) !== JSON.stringify(models);

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
        {t("modelConfig.globalDescription")}
      </p>

      {/* Model 列表 */}
      <div className="grid gap-2 sm:gap-3">
        {localModels.map((model) => (
          <div
            key={model.id}
            className="rounded-xl border border-stone-200/60 bg-white/80 dark:border-stone-700/60 dark:bg-stone-800/80 overflow-hidden transition-all"
          >
            {/* Model Header */}
            <div className="flex items-center justify-between p-3 sm:p-4">
              <div className="flex items-center gap-2.5 sm:gap-3 min-w-0 flex-1">
                <div className="flex h-10 w-10 sm:h-9 sm:w-9 flex-shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-stone-100 to-stone-200 dark:from-stone-700 dark:to-stone-800">
                  <Cpu
                    size={18}
                    className="text-stone-600 dark:text-stone-400"
                  />
                </div>
                <div className="min-w-0 flex-1">
                  <h4 className="text-sm font-medium text-stone-900 dark:text-stone-100 truncate">
                    {model.name}
                  </h4>
                  {model.description && (
                    <div className="text-xs text-stone-500 dark:text-stone-400 truncate hidden sm:block">
                      {model.description}
                    </div>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-2">
                {/* 展开按钮 */}
                <button
                  onClick={() => setExpandedModel(expandedModel === model.id ? null : model.id)}
                  className="text-xs text-stone-400 hover:text-stone-600 dark:hover:text-stone-300 px-2 py-1 rounded hover:bg-stone-100 dark:hover:bg-stone-700"
                  title={t("modelConfig.advancedSettings")}
                >
                  <Settings size={14} />
                </button>

                {/* 开关 */}
                <button
                  onClick={() => toggleModel(model.id)}
                  className={`relative h-7 w-12 sm:h-6 sm:w-11 flex-shrink-0 rounded-full transition-all duration-200 ${
                    model.enabled
                      ? "bg-gradient-to-r from-stone-500 to-stone-600 dark:from-stone-300 dark:to-stone-400"
                      : "bg-stone-200 dark:bg-stone-600"
                  }`}
                  aria-label={
                    model.enabled
                      ? `禁用 ${model.name}`
                      : `启用 ${model.name}`
                  }
                >
                  <span
                    className={`absolute top-0.5 left-0.5 sm:left-0.5 h-6 w-6 sm:h-5 sm:w-5 rounded-full bg-white shadow-md transition-transform duration-200 ${
                      model.enabled
                        ? "translate-x-5 sm:translate-x-5"
                        : "translate-x-0"
                    }`}
                  />
                </button>
              </div>
            </div>

            {/* 展开的 API 配置 */}
            {expandedModel === model.id && (
              <div className="border-t border-stone-200/60 dark:border-stone-700/60 px-4 py-3 bg-stone-50/50 dark:bg-stone-900/30">
                <p className="text-xs text-stone-400 mb-3">
                  {t("modelConfig.perModelOverride")}
                </p>
                <div className="grid gap-2">
                  <div>
                    <label className="block text-xs font-medium text-stone-500 dark:text-stone-400 mb-1">
                      API Base URL
                    </label>
                    <input
                      type="text"
                      value={model.api_base || ""}
                      onChange={(e) => updateModelField(model.id, "api_base", e.target.value || null)}
                      placeholder={t("modelConfig.useProviderDefault")}
                      className="w-full rounded-lg border border-stone-200 bg-white px-3 py-1.5 text-xs text-stone-900 placeholder:text-stone-400 focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400 dark:border-stone-600 dark:bg-stone-700 dark:text-stone-100 dark:placeholder:text-stone-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-stone-500 dark:text-stone-400 mb-1">
                      API Key
                    </label>
                    <div className="relative">
                      <input
                        type={showApiKeys[model.id] ? "text" : "password"}
                        value={model.api_key || ""}
                        onChange={(e) => updateModelField(model.id, "api_key", e.target.value || null)}
                        placeholder={t("modelConfig.useProviderDefault")}
                        className="w-full rounded-lg border border-stone-200 bg-white px-3 py-1.5 pr-8 text-xs text-stone-900 placeholder:text-stone-400 focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400 dark:border-stone-600 dark:bg-stone-700 dark:text-stone-100 dark:placeholder:text-stone-500"
                      />
                      <button
                        type="button"
                        onClick={() =>
                          setShowApiKeys((prev) => ({
                            ...prev,
                            [model.id]: !prev[model.id],
                          }))
                        }
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-stone-400 hover:text-stone-600 dark:hover:text-stone-300"
                      >
                        {showApiKeys[model.id] ? <EyeOff size={12} /> : <Eye size={12} />}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {localModels.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12 text-stone-500 dark:text-stone-400">
          <Cpu size={40} className="mb-3 opacity-30" />
          <p className="text-sm">{t("modelConfig.noModels")}</p>
        </div>
      )}

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

// ============================================
// 角色 Model 分配标签
// ============================================

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
  availableModels: ModelConfig[];
  onUpdate: (roleId: string, modelIds: string[]) => void;
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

  const toggleModel = (modelId: string) => {
    if (!selectedRole) return;
    setLocalRoleModels((prev) => {
      const current = prev[selectedRole] || [];
      if (current.includes(modelId)) {
        return {
          ...prev,
          [selectedRole]: current.filter((id) => id !== modelId),
        };
      }
      return { ...prev, [selectedRole]: [...current, modelId] };
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

  return (
    <div className="space-y-4">
      <p className="text-sm text-stone-500 dark:text-stone-400 px-1">
        {t("modelConfig.rolesDescription")}
      </p>

      {/* 角色选择器 - 手机端下拉菜单 */}
      <div className="block sm:hidden">
        <div className="relative">
          <button
            onClick={() => setRoleDropdownOpen(!roleDropdownOpen)}
            className="flex w-full items-center justify-between rounded-lg border border-stone-300 bg-white px-4 py-3 text-sm font-medium text-stone-900 dark:border-stone-600 dark:bg-stone-800 dark:text-stone-100"
          >
            <span className="flex items-center gap-2">
              <Settings size={16} className="text-stone-500" />
              {selectedRoleData?.name || t("modelConfig.selectRole")}
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
              {t("modelConfig.selectModelsForRole", {
                roleName: selectedRoleData?.name,
              })}
            </h4>
            <div className="grid gap-2 space-y-1 sm:space-y-2">
              {availableModels.map((model) => (
                <label
                  key={model.id}
                  className={`flex cursor-pointer items-center gap-3 rounded-lg bg-white p-3 transition-all dark:bg-stone-800 ${
                    currentRoleModels.includes(model.id)
                      ? "ring-2 ring-stone-500/50 dark:ring-stone-400/50 shadow-sm"
                      : "hover:bg-stone-50 dark:hover:bg-stone-700/50"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={currentRoleModels.includes(model.id)}
                    onChange={() => toggleModel(model.id)}
                    className="h-5 w-5"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-stone-900 dark:text-stone-100 truncate">
                      {model.name}
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

// ============================================
// 主组件
// ============================================

/**
 * Model 配置面板主组件
 */
export function ModelConfigPanel() {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const [activeTab, setActiveTab] = useState<TabType>("providers");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 数据状态
  const [globalModels, setGlobalModels] = useState<ModelConfig[]>([]);
  const [providers, setProviders] = useState<ProviderConfig[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [roleModelsMap, setRoleModelsMap] = useState<
    Record<string, string[]>
  >({});

  const canManage = hasPermission(Permission.MODEL_ADMIN);

  // 加载数据
  const loadData = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const [globalConfig, providerList, roleList] = await Promise.all([
        canManage
          ? modelConfigApi.getGlobalConfig()
          : Promise.resolve(null),
        canManage
          ? modelConfigApi.getProviders()
          : Promise.resolve(null),
        roleApi.list(),
      ]);

      if (globalConfig) {
        setGlobalModels(globalConfig.models || []);
      }
      if (providerList) {
        setProviders(providerList);
      }

      setRoles(roleList || []);

      // 加载角色-models 映射
      if (canManage) {
        const roleModelPromises = (roleList || []).map(async (role) => {
          try {
            const assignment = await modelConfigApi.getRoleModels(role.id);
            return { roleId: role.id, models: assignment.allowed_models };
          } catch {
            return { roleId: role.id, models: [] };
          }
        });
        const roleModelResults = await Promise.all(roleModelPromises);
        const map: Record<string, string[]> = {};
        roleModelResults.forEach(({ roleId, models }) => {
          map[roleId] = models;
        });
        setRoleModelsMap(map);
      }
    } catch (err) {
      const errorMsg = (err as Error).message || t("modelConfig.loadFailed");
      setError(errorMsg);
      toast.error(errorMsg);
    } finally {
      setIsLoading(false);
    }
  }, [canManage, t]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // 更新全局配置
  const handleUpdateGlobalConfig = async (models: ModelConfig[]) => {
    if (!canManage) return;
    setIsSaving(true);
    try {
      await modelConfigApi.updateGlobalConfig(models);
      setGlobalModels(models);
      toast.success(t("modelConfig.saveSuccess"));
    } catch (err) {
      toast.error((err as Error).message || t("modelConfig.saveFailed"));
      throw err;
    } finally {
      setIsSaving(false);
    }
  };

  // 更新 Provider 配置
  const handleUpdateProviders = async (updatedProviders: ProviderConfig[]) => {
    if (!canManage) return;
    setIsSaving(true);
    try {
      await modelConfigApi.updateProviders(updatedProviders);
      setProviders(updatedProviders);
      toast.success(t("modelConfig.saveSuccess"));
    } catch (err) {
      toast.error((err as Error).message || t("modelConfig.saveFailed"));
      throw err;
    } finally {
      setIsSaving(false);
    }
  };

  // 更新角色配置
  const handleUpdateRoleModels = async (
    roleId: string,
    modelIds: string[],
  ) => {
    if (!canManage) return;
    try {
      await modelConfigApi.updateRoleModels(roleId, modelIds);
      setRoleModelsMap((prev) => ({ ...prev, [roleId]: modelIds }));
      toast.success(t("modelConfig.saveSuccess"));
    } catch (err) {
      toast.error((err as Error).message || t("modelConfig.saveFailed"));
      throw err;
    }
  };

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

  const tabs: { key: TabType; label: string }[] = [
    { key: "providers", label: t("modelConfig.providersTab") },
    { key: "global", label: t("modelConfig.globalTab") },
    { key: "roles", label: t("modelConfig.rolesTab") },
  ];

  return (
    <div className="flex h-full flex-col min-h-0">
      {/* 头部 */}
      <PanelHeader
        title={t("modelConfig.title")}
        icon={
          <Cpu size={20} className="text-stone-600 dark:text-stone-400" />
        }
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

      {/* Tab 切换 */}
      {canManage && (
        <div className="flex border-b border-stone-200 dark:border-stone-800">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex-1 px-3 py-4 sm:px-4 sm:py-3 text-center text-sm font-medium transition-all relative ${
                activeTab === tab.key
                  ? "text-stone-900 dark:text-stone-100"
                  : "text-stone-500 hover:text-stone-700 dark:text-stone-400 dark:hover:text-stone-200"
              }`}
            >
              {activeTab === tab.key && (
                <span className="absolute bottom-0 left-2 right-2 h-0.5 rounded-full bg-gradient-to-r from-stone-500 to-stone-600 dark:from-stone-400 dark:to-stone-500" />
              )}
              {tab.label}
            </button>
          ))}
        </div>
      )}

      {/* 内容 */}
      <div className="flex-1 overflow-y-auto px-3 py-4 sm:px-6 sm:py-5">
        {canManage ? (
          activeTab === "providers" ? (
            <ProvidersTab
              providers={providers}
              onUpdate={handleUpdateProviders}
              isLoading={isLoading}
              isSaving={isSaving}
            />
          ) : activeTab === "global" ? (
            <GlobalModelTab
              models={globalModels}
              onUpdate={handleUpdateGlobalConfig}
              isLoading={isLoading}
              isSaving={isSaving}
            />
          ) : (
            <RolesModelTab
              roles={roles}
              roleModelsMap={roleModelsMap}
              availableModels={globalModels}
              onUpdate={handleUpdateRoleModels}
              isLoading={isLoading}
            />
          )
        ) : (
          <div className="flex flex-col items-center justify-center py-12 text-stone-500 dark:text-stone-400">
            <Cpu size={40} className="mb-3 opacity-30" />
            <p className="text-sm">{t("modelConfig.noPermission")}</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default ModelConfigPanel;
