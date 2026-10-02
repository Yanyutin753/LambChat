/**
 * Model 配置管理面板组件
 * 管理员配置角色模型分配和模型配置
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { Button, LoadingSpinner } from "../../common";
import { PanelHeader } from "../../common/PanelHeader";
import { ModelPanelSkeleton } from "../../skeletons";
import { agentConfigApi, roleApi, modelApi } from "../../../services/api";
import type { ModelConfig } from "../../../services/api/model";
import { useAuth } from "../../../hooks/useAuth";
import { Permission } from "../../../types";
import type { Role } from "../../../types";
import { ConfigPanelErrorCallout } from "../ConfigPanelErrorCallout";

import { RolesModelTab, ModelConfigTab } from "./tabs";

type ModelTabType = "roles" | "model-config";

/**
 * Model 管理面板主组件
 */
export function ModelPanel() {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const canManageModels = hasPermission(Permission.MODEL_ADMIN);
  const [activeTab, setActiveTab] = useState<ModelTabType>("roles");
  const [isLoading, setIsLoading] = useState(true);
  const [hasLoaded, setHasLoaded] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const loadGeneration = useRef(0);
  const [error, setError] = useState<string | null>(null);

  // 数据状态
  const [roles, setRoles] = useState<Role[]>([]);
  const [roleModelsMap, setRoleModelsMap] = useState<Record<string, string[]>>(
    {},
  );
  const [availableModels, setAvailableModels] = useState<
    {
      id: string;
      value: string;
      provider?: string;
      icon?: string;
      label: string;
      description?: string;
    }[]
  >([]);
  const [dbModels, setDbModels] = useState<ModelConfig[]>([]);

  // Use a ref for t to avoid loadData re-firing on language changes
  const tRef = useRef(t);
  tRef.current = t;

  // 加载数据
  const loadData = useCallback(async () => {
    const generation = ++loadGeneration.current;
    if (!canManageModels) {
      setIsLoading(false);
      return;
    }

    if (rootRef.current?.contains(document.activeElement)) {
      rootRef.current.focus({ preventScroll: true });
    }
    setIsLoading(true);
    setError(null);

    try {
      // 并行加载所有数据
      const [roleList, modelData] = await Promise.all([
        roleApi.list({ limit: 200 }),
        modelApi.list(true),
      ]);

      // 加载 DB 中的模型配置
      if (generation !== loadGeneration.current) return;
      // 加载角色-models 映射
      const allModelIds = (modelData.models || [])
        .map((model: ModelConfig) => model.id || "")
        .filter(Boolean);
      const roleModelPromises = (roleList.roles || []).map(async (role) => {
        const assignment = await agentConfigApi.getRoleModels(role.id);
        return {
          roleId: role.id,
          models:
            assignment.configured === false
              ? allModelIds
              : assignment.allowed_models,
        };
      });
      const roleModelResults = await Promise.all(roleModelPromises);
      if (generation !== loadGeneration.current) return;
      setDbModels(modelData.models || []);
      setAvailableModels(
        (modelData.models || []).map((m: ModelConfig) => ({
          id: m.id || "",
          value: m.value,
          provider: m.provider,
          icon: m.icon,
          label: m.label,
          description: m.description,
        })),
      );

      // 设置角色列表
      setRoles(roleList.roles || []);

      const modelMap: Record<string, string[]> = {};
      roleModelResults.forEach(({ roleId, models }) => {
        modelMap[roleId] = models;
      });
      setRoleModelsMap(modelMap);
    } catch (err) {
      if (generation !== loadGeneration.current) return;
      const errorMsg =
        (err as Error).message || tRef.current("agentConfig.loadFailed");
      setError(errorMsg);
    } finally {
      if (generation === loadGeneration.current) {
        setIsLoading(false);
        setHasLoaded(true);
      }
    }
  }, [canManageModels]);

  useEffect(() => {
    const requests = loadGeneration;
    loadData();
    return () => {
      requests.current++;
    };
  }, [loadData]);

  // 更新角色模型配置
  const handleUpdateRoleModels = useCallback(
    async (roleId: string, modelValues: string[]) => {
      if (!canManageModels) return;
      await agentConfigApi.updateRoleModels(roleId, modelValues);
      setRoleModelsMap((prev) => ({ ...prev, [roleId]: modelValues }));
      toast.success(t("agentConfig.saveSuccess"));
    },
    [canManageModels, t],
  );

  // 刷新数据
  const handleRefresh = useCallback(() => {
    loadData();
  }, [loadData]);

  if (isLoading && !hasLoaded) {
    return <ModelPanelSkeleton />;
  }

  if (!canManageModels) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-stone-500 dark:text-stone-400">
          {t("agentConfig.noPermission")}
        </p>
      </div>
    );
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
        title={t("agentConfig.modelTitle")}
        subtitle={t("agentConfig.modelConfigDescription")}
        illustration="panel-models"
        actions={
          <Button
            onClick={handleRefresh}
            disabled={isLoading}
            leftIcon={<RefreshCw size={16} />}
            aria-label={t("common.refresh")}
          >
            <span className="hidden sm:inline text-14">
              {t("common.refresh")}
            </span>
          </Button>
        }
      />

      {error && (
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
      )}
      {isLoading && (
        <div
          role="status"
          className="panel-body flex items-center gap-2 text-14 text-theme-text-secondary"
        >
          <LoadingSpinner size="sm" />
          {t("common.loading")}
        </div>
      )}
      <div
        hidden={Boolean(error)}
        inert={isLoading || undefined}
        className={error ? "hidden" : "flex min-h-0 flex-1 flex-col"}
      >
        {/* Tab 切换 */}
        <div className="inline-grid grid-cols-2 rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg-subtle)] p-1 my-3">
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
            {t("agentConfig.modelsTab")}
          </button>
          <button
            type="button"
            aria-pressed={activeTab === "model-config"}
            onClick={() => setActiveTab("model-config")}
            className={`flex items-center justify-center gap-2 rounded-md px-3 py-2 text-14 font-medium min-h-11 transition-colors duration-150 motion-reduce:transition-none focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)] ${
              activeTab === "model-config"
                ? "bg-white text-stone-950 shadow-sm ring-1 ring-[var(--glass-border)] dark:bg-stone-800 dark:text-stone-50"
                : "text-stone-500 hover:bg-white/60 hover:text-stone-800 dark:text-stone-400 dark:hover:bg-stone-800/60 dark:hover:text-stone-100"
            }`}
          >
            {t("agentConfig.modelConfigTab")}
          </button>
        </div>

        {/* 内容 */}
        <div className="panel-body flex-1 overflow-y-auto">
          <div hidden={activeTab !== "model-config"}>
            <ModelConfigTab models={dbModels} onReload={loadData} />
          </div>
          <div hidden={activeTab !== "roles"}>
            <RolesModelTab
              roles={roles}
              roleModelsMap={roleModelsMap}
              availableModels={availableModels}
              onUpdate={handleUpdateRoleModels}
              isLoading={false}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

export default ModelPanel;
