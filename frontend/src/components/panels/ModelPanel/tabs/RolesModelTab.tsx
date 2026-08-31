import { useState, useEffect, useMemo } from "react";
import { Cpu, Save, List, ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ModelPanelSkeleton } from "../../../skeletons";
import { RoleSelector } from "../../AgentPanel/shared/RoleSelector";
import { ModelIconImg } from "../../../agent/modelIcon.tsx";
import { Checkbox } from "../../../common/Checkbox";
import { Button } from "../../../common";
import { EmptyState } from "../../../common/EmptyState";
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
  const [expandedModel, setExpandedModel] = useState<string | null>(null);

  const toggleExpand = (id: string) =>
    setExpandedModel((prev) => (prev === id ? null : id));

  useEffect(() => {
    setLocalRoleModels(roleModelsMap);
  }, [roleModelsMap]);

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
      <EmptyState
        icon={<Cpu size={28} />}
        title={t("agentConfig.noModelsConfigured")}
        description={t("agentConfig.noModelsConfiguredHint")}
      />
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
    <div className="space-y-4 animate-glass-enter">
      <p className="hidden px-1 text-sm leading-relaxed text-stone-500 sm:block dark:text-stone-400">
        {t("agentConfig.modelsDescription")}
      </p>

      <RoleSelector
        roles={roles}
        selectedRoleId={selectedRole}
        onSelectRole={setSelectedRole}
      />

      {selectedRole && (
        <>
          <div className="agent-config-list overflow-hidden rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg)] divide-y divide-[var(--glass-border)]">
            {/* Header row */}
            <div className="flex items-center justify-between gap-3 font-serif bg-[var(--glass-bg-subtle)] px-3.5 py-2.5 sm:px-4">
              <h4 className="min-w-0 truncate text-xs font-medium uppercase tracking-wider text-stone-500 dark:text-stone-400">
                {t("agentConfig.selectModelsForRole", {
                  roleName: selectedRoleData?.name,
                })}
              </h4>
              <div className="flex items-center gap-1">
                <button
                  onClick={handleSelectAll}
                  className="text-xs px-2 py-1 rounded-md text-stone-500 hover:text-stone-700 hover:bg-white/50 dark:text-stone-400 dark:hover:text-stone-200 dark:hover:bg-stone-700/40 transition-colors duration-150"
                >
                  {t("agentConfig.selectAll")}
                </button>
                <span className="text-stone-300 dark:text-stone-600">|</span>
                <button
                  onClick={handleClearAll}
                  className="text-xs px-2 py-1 rounded-md text-stone-500 hover:text-stone-700 hover:bg-white/50 dark:text-stone-400 dark:hover:text-stone-200 dark:hover:bg-stone-700/40 transition-colors duration-150"
                >
                  {t("agentConfig.clearAll")}
                </button>
              </div>
            </div>

            {/* Status pill */}
            <div className="px-3.5 py-2 sm:px-4">
              <div className="glass-pill glass-pill--info">
                <List size={14} />
                <span>
                  {t("agentConfig.selectedModelsCount", {
                    count: currentRoleModels.length,
                    total: availableModels.length,
                  })}
                </span>
              </div>
            </div>

            {/* Model rows */}
            <div className="divide-y divide-[var(--glass-border)]">
              {availableModels.map((model) => {
                const isSelected = currentRoleModels.includes(model.id);
                const hasDesc = !!model.description;
                return (
                  <div
                    key={model.id}
                    className={`transition-colors duration-150 ${
                      isSelected
                        ? "bg-[var(--glass-bg-subtle)]"
                        : "hover:bg-[var(--glass-bg-hover)]"
                    }`}
                  >
                    <label className="flex min-h-14 cursor-pointer items-center gap-3 px-3.5 py-3 sm:px-4 sm:gap-3.5">
                      <Checkbox
                        checked={isSelected}
                        onChange={() => toggleModel(model.id)}
                        size="sm"
                      />
                      <ModelIconImg
                        model={model.value}
                        provider={model.provider}
                        icon={model.icon}
                        size={20}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium font-serif text-stone-950 dark:text-stone-100">
                          {model.label}
                        </div>
                        <div className="text-xs font-mono text-stone-400 dark:text-stone-500 truncate sm:hidden mt-0.5">
                          {model.value}
                        </div>
                      </div>
                      <span className="text-xs font-mono text-stone-400 dark:text-stone-500 truncate max-w-[140px] hidden sm:inline">
                        {model.value}
                      </span>
                      {hasDesc && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.preventDefault();
                            toggleExpand(model.id);
                          }}
                          className="shrink-0 p-0.5 rounded-md text-stone-400 hover:text-stone-600 dark:hover:text-stone-300 transition-colors"
                        >
                          <ChevronDown
                            size={14}
                            className={`transition-transform duration-200 ${
                              expandedModel === model.id ? "rotate-180" : ""
                            }`}
                          />
                        </button>
                      )}
                    </label>
                    {expandedModel === model.id && hasDesc && (
                      <div className="px-3.5 pb-3 pl-[3.25rem] pt-0 sm:px-4 sm:pl-[3.75rem]">
                        <p className="text-xs text-stone-500 dark:text-stone-400 leading-relaxed">
                          {model.description}
                        </p>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {hasChanges && (
            <div className="flex items-center justify-end">
              <Button
                variant="primary"
                onClick={handleSave}
                loading={isSaving}
                leftIcon={<Save size={16} />}
                className="px-5 py-2.5 text-sm"
              >
                {t("common.save")}
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
