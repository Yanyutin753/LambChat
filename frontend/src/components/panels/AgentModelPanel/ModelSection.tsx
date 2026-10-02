/**
 * Model 配置区块（嵌入统一面板内，不再自带外壳）
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { Button, LoadingSpinner } from "../../common";
import { ModelSectionSkeleton } from "../../skeletons";
import { agentConfigApi, roleApi, modelApi } from "../../../services/api";
import type { ModelConfig } from "../../../services/api/model";
import { useAuth } from "../../../hooks/useAuth";
import { Permission } from "../../../types";
import type { Role } from "../../../types";
import { ConfigPanelErrorCallout } from "../ConfigPanelErrorCallout";

import { RolesModelTab, ModelConfigTab } from "../ModelPanel/tabs";

type ModelTabType = "roles" | "model-config";

export function ModelSection() {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const canManageModels = hasPermission(Permission.MODEL_ADMIN);
  const [activeTab, setActiveTab] = useState<ModelTabType>("roles");
  const [isLoading, setIsLoading] = useState(true);
  const [hasLoaded, setHasLoaded] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const loadGeneration = useRef(0);
  const [error, setError] = useState<string | null>(null);

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

  const tRef = useRef(t);
  tRef.current = t;

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
      const [roleList, modelData] = await Promise.all([
        roleApi.list({ limit: 200 }),
        modelApi.list(true),
      ]);

      if (generation !== loadGeneration.current) return;
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

  const handleUpdateRoleModels = useCallback(
    async (roleId: string, modelValues: string[]) => {
      if (!canManageModels) return;
      await agentConfigApi.updateRoleModels(roleId, modelValues);
      setRoleModelsMap((prev) => ({ ...prev, [roleId]: modelValues }));
      toast.success(t("agentConfig.saveSuccess"));
    },
    [canManageModels, t],
  );

  if (isLoading && !hasLoaded) {
    return <ModelSectionSkeleton />;
  }

  if (!canManageModels) {
    return (
      <div className="flex h-48 items-center justify-center">
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
      className="panel-body panel-stack focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)]"
    >
      {error && (
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
      )}
      {isLoading && (
        <div
          role="status"
          className="flex items-center gap-2 text-14 text-theme-text-secondary"
        >
          <LoadingSpinner size="sm" />
          {t("common.loading")}
        </div>
      )}
      <div
        hidden={Boolean(error)}
        inert={isLoading || undefined}
        className={error ? "hidden" : "panel-stack"}
      >
        <div className="inline-grid grid-cols-2 rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg-subtle)] p-1 self-start max-w-full font-serif">
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
  );
}
