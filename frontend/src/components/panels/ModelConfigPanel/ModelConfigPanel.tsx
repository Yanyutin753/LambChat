/**
 * Model 配置管理面板组件
 * 管理员配置 Provider 分组、凭证和模型
 */
import { useState, useEffect, useCallback, type RefObject } from "react";
import {
  Cpu,
  AlertCircle,
  RefreshCw,
  LayoutGrid,
  Shield,
  Plus,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { PanelHeader } from "../../common/PanelHeader";
import { LoadingSpinner } from "../../common/LoadingSpinner";
import { modelConfigApi, roleApi } from "../../../services/api";
import { useAuth } from "../../../hooks/useAuth";
import { useSwipeToClose } from "../../../hooks/useSwipeToClose";
import { Permission } from "../../../types";
import type { ModelProviderConfig, ModelConfig, Role } from "../../../types";
import { ProviderEditor, ProvidersTab, RolesTab } from "./components";

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
  const [legacyMigrationApplied, setLegacyMigrationApplied] = useState(false);
  const [legacyInheritedProviders, setLegacyInheritedProviders] = useState<
    string[]
  >([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [roleModelsMap, setRoleModelsMap] = useState<Record<string, string[]>>(
    {},
  );
  const [showProviderModal, setShowProviderModal] = useState(false);
  const [editingProviderIndex, setEditingProviderIndex] = useState<
    number | null
  >(null);
  const [editingProvider, setEditingProvider] =
    useState<ModelProviderConfig | null>(null);

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
        setLegacyMigrationApplied(providerConfig.legacy_migration_applied);
        setLegacyInheritedProviders(
          providerConfig.legacy_inherited_providers || [],
        );
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
      setLegacyMigrationApplied(false);
      setLegacyInheritedProviders([]);
      toast.success(t("modelConfig.saveSuccess"));
    } catch (err) {
      toast.error((err as Error).message || t("modelConfig.saveFailed"));
      throw err;
    } finally {
      setIsSaving(false);
    }
  };

  const buildNewProvider = useCallback(
    (): ModelProviderConfig => ({
      provider: "openai",
      label: t("modelConfig.newProvider"),
      base_url: undefined,
      api_key: undefined,
      has_api_key: false,
      clear_api_key: false,
      temperature: 0.7,
      max_tokens: 4096,
      max_retries: 3,
      retry_delay: 1.0,
      models: [],
      provider_type: "openai_compatible",
    }),
    [t],
  );

  const closeProviderModal = useCallback(() => {
    setShowProviderModal(false);
    setEditingProviderIndex(null);
    setEditingProvider(null);
  }, []);

  const handleAddProvider = useCallback(() => {
    setEditingProviderIndex(null);
    setEditingProvider(buildNewProvider());
    setShowProviderModal(true);
  }, [buildNewProvider]);

  const handleEditProvider = useCallback((index: number) => {
    setEditingProviderIndex(index);
    setEditingProvider(providers[index]);
    setShowProviderModal(true);
  }, [providers]);

  const handleDeleteProvider = useCallback(
    async (index: number) => {
      if (!canManage) return;
      try {
        await handleSaveProviders(providers.filter((_, i) => i !== index));
      } catch {
        // toast already handled in save flow
      }
    },
    [canManage, handleSaveProviders, providers],
  );

  const handleSaveProvider = useCallback(
    async (updatedProvider: ModelProviderConfig) => {
      if (!canManage) return;

      const nextProviders =
        editingProviderIndex === null
          ? [...providers, updatedProvider]
          : providers.map((provider, index) =>
              index === editingProviderIndex ? updatedProvider : provider,
            );

      try {
        await handleSaveProviders(nextProviders);
        closeProviderModal();
      } catch {
        // toast already handled in save flow
      }
    },
    [
      canManage,
      closeProviderModal,
      editingProviderIndex,
      handleSaveProviders,
      providers,
    ],
  );

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

  const providerSwipeRef = useSwipeToClose({
    onClose: closeProviderModal,
    enabled: showProviderModal,
  });

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <div className="model-config-shell flex h-full min-h-0 flex-col">
      <PanelHeader
        title={t("modelConfig.title")}
        subtitle={t("modelConfig.subtitle")}
        icon={<Cpu size={20} className="text-stone-600 dark:text-stone-400" />}
        actions={
          <>
            {canManage && activeTab === "providers" && (
              <button onClick={handleAddProvider} className="btn-primary">
                <Plus size={16} />
                <span className="hidden sm:inline">
                  {t("modelConfig.addProvider")}
                </span>
              </button>
            )}
            <button
              onClick={loadData}
              className="btn-secondary"
            >
              <RefreshCw
                size={16}
                className="hover:rotate-180 transition-transform duration-500"
              />
              <span className="hidden sm:inline">{t("common.refresh")}</span>
            </button>
          </>
        }
      />

      {error && (
        <div className="model-config-banner model-config-banner--error mx-4 mt-4 flex items-center gap-3 rounded-2xl p-4 text-sm sm:mx-6">
          <AlertCircle size={20} className="flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {canManage && (
        <div className="mx-4 mt-3 sm:mx-6 sm:mt-4">
          <div className="model-config-tabs">
            <button
              onClick={() => setActiveTab("providers")}
              className={`model-config-tab ${activeTab === "providers" ? "is-active" : ""}`}
            >
              <LayoutGrid size={15} style={{ color: "var(--theme-primary)" }} />
              {t("modelConfig.providersTab")}
            </button>
            <button
              onClick={() => setActiveTab("roles")}
              className={`model-config-tab ${activeTab === "roles" ? "is-active" : ""}`}
            >
              <Shield size={15} style={{ color: "var(--theme-primary)" }} />
              {t("modelConfig.rolesTab")}
            </button>
          </div>
        </div>
      )}

      <div className="model-config-content flex-1 overflow-y-auto px-4 py-5 sm:px-6 sm:py-6">
        {canManage ? (
          activeTab === "providers" ? (
            <ProvidersTab
              providers={providers}
              legacyMigrationApplied={legacyMigrationApplied}
              legacyInheritedProviders={legacyInheritedProviders}
              onAdd={handleAddProvider}
              onEdit={handleEditProvider}
              onDelete={handleDeleteProvider}
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
          <div className="model-config-empty flex flex-col items-center justify-center rounded-3xl border border-stone-200 bg-white px-6 py-16 text-center shadow-sm dark:border-stone-700 dark:bg-stone-800 sm:py-20">
            <div className="model-config-empty-icon mb-6 flex h-24 w-24 items-center justify-center rounded-3xl">
              <Cpu size={40} style={{ color: "var(--theme-primary)" }} />
            </div>
            <p className="mb-2 text-base font-semibold text-[var(--theme-text)]">
              {t("modelConfig.noPermission")}
            </p>
            <p className="mt-1 max-w-[320px] text-sm text-[var(--theme-text-secondary)]">
              You need admin permissions to manage models
            </p>
          </div>
        )}
      </div>

      {showProviderModal && editingProvider && (
        <>
          <div className="fixed inset-0" onClick={closeProviderModal} />
          <div
            ref={providerSwipeRef as RefObject<HTMLDivElement>}
            className="modal-bottom-sheet sm:modal-centered-wrapper"
          >
            <div
              className="modal-bottom-sheet-content sm:modal-centered-content sm:max-w-[72rem]"
            >
              <div className="bottom-sheet-handle sm:hidden" />
              <div
                className="flex items-center justify-between border-b px-6 py-4"
                style={{
                  borderColor: "var(--theme-border)",
                }}
              >
                <h3
                  className="font-serif text-xl font-semibold"
                  style={{ color: "var(--theme-text)" }}
                >
                  {editingProviderIndex === null
                    ? t("modelConfig.addProvider")
                    : t("modelConfig.editProvider", {
                        name: editingProvider.label || editingProvider.provider,
                      })}
                </h3>
                <button onClick={closeProviderModal} className="btn-icon">
                  <X size={20} />
                </button>
              </div>

              <div className="px-4 py-4 sm:flex-1 sm:overflow-y-auto sm:px-6">
                <ProviderEditor
                  provider={editingProvider}
                  isLegacyInherited={legacyInheritedProviders.includes(
                    editingProvider.provider,
                  )}
                  onUpdate={handleSaveProvider}
                  showDelete={editingProviderIndex !== null}
                  onDelete={() => {
                    if (editingProviderIndex !== null) {
                      void handleDeleteProvider(editingProviderIndex);
                    }
                    closeProviderModal();
                  }}
                />
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default ModelConfigPanel;
