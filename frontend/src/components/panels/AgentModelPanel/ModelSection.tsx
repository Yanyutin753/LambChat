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
  const { hasPermission, user: actor } = useAuth();
  const isSystemAdmin = hasPermission(Permission.SYSTEM_ADMIN);
  const canReadModels = hasPermission(Permission.MODEL_READ);
  const canAssignModels = hasPermission(Permission.MODEL_ASSIGN);
  const [activeTab, setActiveTab] = useState<ModelTabType>(
    canAssignModels ? "roles" : "model-config",
  );
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
    if (!canReadModels && !canAssignModels) {
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
        canAssignModels
          ? roleApi.list({ limit: 200 })
          : Promise.resolve({ roles: [] }),
        canReadModels ? modelApi.list(true) : Promise.resolve({ models: [] }),
      ]);

      if (generation !== loadGeneration.current) return;
      roleList.roles = (roleList.roles || []).filter(
        (role) =>
          isSystemAdmin || actor?.assignable_role_ids?.includes(role.id),
      );
      const roleModelPromises = (roleList.roles || []).map(async (role) => {
        const assignment = await agentConfigApi.getRoleModels(role.id);
        return {
          roleId: role.id,
          models: assignment.allowed_models,
        };
      });
      const roleModelResults = await Promise.all(roleModelPromises);
      if (generation !== loadGeneration.current) return;
      setDbModels(modelData.models || []);
      const assignmentModels =
        canAssignModels && (!isSystemAdmin || !canReadModels)
          ? await modelApi.listAvailable()
          : modelData;
      if (generation !== loadGeneration.current) return;
      setAvailableModels(
        (assignmentModels.models || []).map((m) => ({
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
  }, [
    canReadModels,
    canAssignModels,
    isSystemAdmin,
    actor?.assignable_role_ids,
  ]);

  useEffect(() => {
    const requests = loadGeneration;
    loadData();
    return () => {
      requests.current++;
    };
  }, [loadData]);

  const handleUpdateRoleModels = useCallback(
    async (roleId: string, modelValues: string[]) => {
      if (!canAssignModels) return;
      await agentConfigApi.updateRoleModels(roleId, modelValues);
      setRoleModelsMap((prev) => ({ ...prev, [roleId]: modelValues }));
      toast.success(t("agentConfig.saveSuccess"));
    },
    [canAssignModels, t],
  );

  if (isLoading && !hasLoaded) {
    return <ModelSectionSkeleton />;
  }

  if (!canReadModels && !canAssignModels) {
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
            disabled={!canAssignModels}
            aria-pressed={activeTab === "roles"}
            onClick={() => setActiveTab("roles")}
            className={`flex items-center justify-center gap-2 rounded-md px-3 py-2 text-14 font-medium min-h-11 transition-colors duration-150 motion-reduce:transition-none focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)] ${
              activeTab === "roles"
                ? "bg-theme-bg-card text-theme-text shadow-sm ring-1 ring-[var(--glass-border)] dark:bg-stone-800 dark:text-stone-50"
                : "text-theme-text-secondary hover:bg-theme-bg-hover hover:text-theme-text dark:text-stone-400 dark:hover:bg-theme-bg-hover dark:hover:text-stone-100"
            }`}
          >
            {t("agentConfig.modelsTab")}
          </button>
          <button
            type="button"
            disabled={!canReadModels}
            aria-pressed={activeTab === "model-config"}
            onClick={() => setActiveTab("model-config")}
            className={`flex items-center justify-center gap-2 rounded-md px-3 py-2 text-14 font-medium min-h-11 transition-colors duration-150 motion-reduce:transition-none focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)] ${
              activeTab === "model-config"
                ? "bg-theme-bg-card text-theme-text shadow-sm ring-1 ring-[var(--glass-border)] dark:bg-stone-800 dark:text-stone-50"
                : "text-theme-text-secondary hover:bg-theme-bg-hover hover:text-theme-text dark:text-stone-400 dark:hover:bg-theme-bg-hover dark:hover:text-stone-100"
            }`}
          >
            {t("agentConfig.modelConfigTab")}
          </button>
        </div>

        <div hidden={!canReadModels || activeTab !== "model-config"}>
          <ModelConfigTab models={dbModels} onReload={loadData} />
        </div>
        <div hidden={!canAssignModels || activeTab !== "roles"}>
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
