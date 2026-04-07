/**
 * Model 配置管理面板组件
 * 管理员配置 Provider 分组、凭证和模型
 */
import { useState, useEffect, useCallback } from "react";
import { Cpu, AlertCircle, RefreshCw, LayoutGrid, Shield } from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { PanelHeader } from "../../common/PanelHeader";
import { LoadingSpinner } from "../../common/LoadingSpinner";
import { modelConfigApi, roleApi } from "../../../services/api";
import { useAuth } from "../../../hooks/useAuth";
import { Permission } from "../../../types";
import type { ModelProviderConfig, ModelConfig, Role } from "../../../types";
import { ProvidersTab, RolesTab } from "./components";

// Tab types
type TabType = "providers" | "roles";

// ============================================
// Main Panel
// ====================================

export function ModelConfigPanel() {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const [activeTab, setActiveTab] = useState<TabType>("providers");
  const [isLoading, setIsLoading] = useState(true);
  const [_isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [providers, setProviders] = useState<ModelProviderConfig[]>([]);
  const [flatModels, setFlatModels] = useState<ModelConfig[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [roleModelsMap, setRoleModelsMap] = useState<Record<string, string[]>>(
    {},
  );

  const canManage = hasPermission(Permission.MODEL_ADMIN);

  const loadData = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const [providerConfig, roleList] = await Promise.all([
        canManage ? modelConfigApi.getProviderConfig() : Promise.resolve(null),
        roleApi.list(),
      ]);

      if (providerConfig) {
        setProviders(providerConfig.providers);
        setFlatModels(providerConfig.flat_models);
      }

      setRoles(roleList || []);

      if (canManage) {
        const roleModelPromises = (roleList || []).map(async (role: Role) => {
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

  const handleSaveProviders = async (newProviders: ModelProviderConfig[]) => {
    if (!canManage) return;
    setIsSaving(true);
    try {
      const result = await modelConfigApi.updateProviderConfig(newProviders);
      setProviders(result.providers);
      setFlatModels(result.flat_models);
      toast.success(t("modelConfig.saveSuccess"));
    } catch (err) {
      toast.error((err as Error).message || t("modelConfig.saveFailed"));
      throw err;
    } finally {
      setIsSaving(false);
    }
  };

  const handleAddProvider = () => {
    const newProvider: ModelProviderConfig = {
      provider: "openai",
      label: t("modelConfig.newProvider"),
      base_url: undefined,
      api_key: undefined,
      temperature: 0.7,
      max_tokens: 4096,
      max_retries: 3,
      retry_delay: 1.0,
      models: [],
    };
    setProviders([...providers, newProvider]);
  };

  const handleUpdateRoleModels = async (roleId: string, modelIds: string[]) => {
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

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col min-h-0">
      <PanelHeader
        title={t("modelConfig.title")}
        icon={<Cpu size={20} className="text-stone-600 dark:text-stone-400" />}
        actions={
          <button
            onClick={loadData}
            className="flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-medium transition-all duration-200 active:scale-95"
            style={{ color: "var(--theme-text-secondary)" }}
          >
            <RefreshCw
              size={16}
              className="hover:rotate-180 transition-transform duration-500"
            />
            <span className="hidden sm:inline">{t("common.refresh")}</span>
          </button>
        }
      />

      {error && (
        <div
          className="mx-4 mt-4 flex items-center gap-3 rounded-2xl p-4 text-sm sm:mx-6"
          style={{
            background: "rgba(239, 68, 68, 0.08)",
            color: "#ef4444",
            border: "1px solid rgba(239, 68, 68, 0.2)",
          }}
        >
          <AlertCircle size={20} className="flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {canManage && (
        <div className="mx-4 mt-3 sm:mx-6 sm:mt-4">
          <div
            className="inline-flex gap-1 p-1.5 rounded-2xl"
            style={{ background: "var(--theme-bg)" }}
          >
            <button
              onClick={() => setActiveTab("providers")}
              className="px-5 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 flex items-center gap-2 min-w-[110px] justify-center"
              style={
                activeTab === "providers"
                  ? {
                      background: "var(--theme-bg-card)",
                      color: "var(--theme-text)",
                      boxShadow: "0 2px 8px rgba(0,0,0,0.12)",
                    }
                  : {
                      color: "var(--theme-text-secondary)",
                      background: "transparent",
                    }
              }
            >
              <LayoutGrid size={16} style={{ color: "var(--theme-primary)" }} />
              {t("modelConfig.providersTab")}
            </button>
            <button
              onClick={() => setActiveTab("roles")}
              className="px-5 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 flex items-center gap-2 min-w-[110px] justify-center"
              style={
                activeTab === "roles"
                  ? {
                      background: "var(--theme-bg-card)",
                      color: "var(--theme-text)",
                      boxShadow: "0 2px 8px rgba(0,0,0,0.12)",
                    }
                  : {
                      color: "var(--theme-text-secondary)",
                      background: "transparent",
                    }
              }
            >
              <Shield size={16} style={{ color: "var(--theme-primary)" }} />
              {t("modelConfig.rolesTab")}
            </button>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-4 py-5 sm:px-6 sm:py-6">
        {canManage ? (
          activeTab === "providers" ? (
            <ProvidersTab
              providers={providers}
              onUpdate={handleSaveProviders}
              onAdd={handleAddProvider}
            />
          ) : (
            <RolesTab
              roles={roles}
              roleModelsMap={roleModelsMap}
              flatModels={flatModels}
              onUpdate={handleUpdateRoleModels}
              isLoading={isLoading}
            />
          )
        ) : (
          <div
            className="flex flex-col items-center justify-center py-20 rounded-3xl"
            style={{ background: "var(--theme-bg)" }}
          >
            <div
              className="w-24 h-24 rounded-3xl flex items-center justify-center mb-6"
              style={{
                background: "var(--theme-primary-light)",
                boxShadow: "0 8px 32px rgba(0,0,0,0.08)",
              }}
            >
              <Cpu size={40} style={{ color: "var(--theme-primary)" }} />
            </div>
            <p
              className="text-base font-semibold mb-2"
              style={{ color: "var(--theme-text)" }}
            >
              {t("modelConfig.noPermission")}
            </p>
            <p
              className="text-sm mt-1 max-w-[260px] text-center"
              style={{ color: "var(--theme-text-secondary)" }}
            >
              You need admin permissions to manage models
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

export default ModelConfigPanel;
