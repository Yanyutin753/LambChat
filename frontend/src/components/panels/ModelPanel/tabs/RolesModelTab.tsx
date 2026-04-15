import { useState, useEffect, useMemo } from "react";
import { Cpu, Save, Globe, List } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ModelPanelSkeleton } from "../../../skeletons";
import { RoleSelector } from "../../AgentPanel/shared/RoleSelector";
import { ModelIconImg } from "../../../agent/modelIcon.tsx";
import type { ModelOption } from "../../../../services/api/model";
import type { Role } from "../../../../types";

interface RolesModelTabProps {
  roles: Role[];
  roleModelsMap: Record<string, string[]>;
  availableModels: ModelOption[];
  onUpdate: (roleId: string, modelValues: string[]) => Promise<void>;
  isLoading: boolean;
}

export function RolesModelTab({
  roles,
  roleModelsMap,
  availableModels,
  onUpdate,
  isLoading,
}: RolesModelTabProps) {
  const { t } = useTranslation();
  const [selectedRole, setSelectedRole] = useState<string | null>(
    roles.length > 0 ? roles[0].id : null,
  );
  const [localRoleModels, setLocalRoleModels] =
    useState<Record<string, string[]>>(roleModelsMap);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    setLocalRoleModels(roleModelsMap);
  }, [roleModelsMap]);

  // Reset selectedRole if it no longer exists in the roles list
  useEffect(() => {
    if (selectedRole && !roles.find((r) => r.id === selectedRole)) {
      setSelectedRole(roles.length > 0 ? roles[0].id : null);
    }
  }, [roles, selectedRole]);

  const hasChanges = useMemo(() => {
    if (!selectedRole) return false;
    const local = localRoleModels[selectedRole];
    const original = roleModelsMap[selectedRole];
    if (!local && !original) return false;
    if (!local || !original) return true;
    if (local.length !== original.length) return true;
    return local.some((v, i) => v !== original[i]);
  }, [selectedRole, localRoleModels, roleModelsMap]);

  if (isLoading) {
    return <ModelPanelSkeleton />;
  }

  if (availableModels.length === 0) {
    return (
      <div className="skill-empty-state">
        <Cpu size={28} className="skill-empty-state__icon" />
        <p className="skill-empty-state__title">
          {t("agentConfig.noModelsConfigured")}
        </p>
        <p className="skill-empty-state__description">
          {t("agentConfig.noModelsConfiguredHint")}
        </p>
      </div>
    );
  }

  const currentRoleModels = selectedRole
    ? localRoleModels[selectedRole] || []
    : [];
  const isAllModels = currentRoleModels.length === 0;

  const toggleModel = (modelId: string) => {
    if (!selectedRole) return;
    setLocalRoleModels((prev) => {
      const current = prev[selectedRole] || [];
      if (current.includes(modelId)) {
        return {
          ...prev,
          [selectedRole]: current.filter((v) => v !== modelId),
        };
      }
      return { ...prev, [selectedRole]: [...current, modelId] };
    });
  };

  const handleSelectAll = () => {
    if (!selectedRole) return;
    setLocalRoleModels((prev) => ({
      ...prev,
      [selectedRole]: availableModels.map((m) => m.id),
    }));
  };

  const handleClearAll = () => {
    if (!selectedRole) return;
    setLocalRoleModels((prev) => ({
      ...prev,
      [selectedRole]: [],
    }));
  };

  const handleSave = async () => {
    if (!selectedRole) return;
    setIsSaving(true);
    try {
      await onUpdate(selectedRole, localRoleModels[selectedRole] || []);
    } catch (err) {
      console.error("Failed to save role models:", err);
    } finally {
      setIsSaving(false);
    }
  };

  const selectedRoleData = roles.find((r) => r.id === selectedRole);

  return (
    <div className="space-y-4 sm:space-y-5 animate-glass-enter">
      <p className="text-sm text-stone-500 dark:text-stone-400 px-1 leading-relaxed hidden sm:block">
        {t("agentConfig.modelsDescription")}
      </p>

      <RoleSelector
        roles={roles}
        selectedRoleId={selectedRole}
        onSelectRole={setSelectedRole}
      />

      {selectedRole && (
        <>
          <div className="glass-card rounded-xl">
            <div className="px-4 sm:px-5 pt-3.5 sm:pt-4 pb-2.5 sm:pb-3 flex items-center justify-between">
              <h4 className="text-sm font-medium text-stone-900 dark:text-stone-100">
                {t("agentConfig.selectModelsForRole", {
                  roleName: selectedRoleData?.name,
                })}
              </h4>
              <div className="flex items-center gap-1.5">
                <button
                  onClick={handleSelectAll}
                  className="text-xs px-2 py-1 rounded-lg text-stone-500 hover:text-stone-700 hover:bg-white/50 dark:text-stone-400 dark:hover:text-stone-200 dark:hover:bg-stone-700/40 transition-all duration-200"
                >
                  {t("agentConfig.selectAll")}
                </button>
                <button
                  onClick={handleClearAll}
                  className="text-xs px-2 py-1 rounded-lg text-stone-500 hover:text-stone-700 hover:bg-white/50 dark:text-stone-400 dark:hover:text-stone-200 dark:hover:bg-stone-700/40 transition-all duration-200"
                >
                  {t("agentConfig.clearAll")}
                </button>
              </div>
            </div>

            {/* Status indicator */}
            <div className="px-4 sm:px-5 pb-2.5 sm:pb-3">
              {isAllModels ? (
                <div className="glass-pill glass-pill--active">
                  <Globe size={14} />
                  <span>{t("agentConfig.allModelsAvailable")}</span>
                </div>
              ) : (
                <div className="glass-pill glass-pill--info">
                  <List size={14} />
                  <span>
                    {t("agentConfig.selectedModelsCount", {
                      count: currentRoleModels.length,
                      total: availableModels.length,
                    })}
                  </span>
                </div>
              )}
            </div>

            <div className="px-2.5 sm:px-3 pb-2.5 sm:pb-3 space-y-1">
              {availableModels.map((model) => {
                const isSelected = currentRoleModels.includes(model.id);
                return (
                  <label
                    key={model.id}
                    className={`flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 sm:py-3 sm:gap-3.5 transition-all duration-200 ${
                      isSelected
                        ? "glass-card"
                        : "hover:bg-white/50 dark:hover:bg-stone-800/40"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleModel(model.id)}
                      className="h-4 w-4 rounded border-stone-300 text-stone-600 focus:ring-stone-500"
                    />
                    <ModelIconImg
                      model={model.value}
                      provider={model.provider}
                      size={20}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium text-stone-900 dark:text-stone-100 truncate">
                        {model.label}
                      </div>
                      <div className="text-xs font-mono text-stone-400 dark:text-stone-500 truncate sm:hidden mt-0.5">
                        {model.value}
                      </div>
                      {model.description && (
                        <div className="text-xs text-stone-500 dark:text-stone-400 mt-0.5 hidden sm:block">
                          {model.description}
                        </div>
                      )}
                    </div>
                    <span className="text-xs font-mono text-stone-400 dark:text-stone-500 truncate max-w-[140px] hidden sm:inline">
                      {model.value}
                    </span>
                  </label>
                );
              })}
            </div>
          </div>

          {hasChanges && (
            <div className="flex justify-end">
              <button
                onClick={handleSave}
                disabled={isSaving}
                className="btn-primary flex items-center gap-2 px-5 py-2.5 text-sm disabled:opacity-50 hover:shadow-lg hover:shadow-stone-500/10 transition-shadow duration-200"
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
