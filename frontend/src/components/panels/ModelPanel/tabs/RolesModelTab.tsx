import { Cpu } from "lucide-react";
import { Pagination } from "../../../common/Pagination";
import { useClientPagination } from "../../../../hooks/useClientPagination";
import { useState, useEffect, useRef, useId } from "react";
import { Save, ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ModelPanelSkeleton } from "../../../skeletons";
import { RoleSelector } from "../../AgentPanel/shared/RoleSelector";
import { ModelIconImg } from "../../../agent/modelIcon.tsx";
import { Checkbox } from "../../../common/Checkbox";
import { Button, IconButton } from "../../../common";
import { ConfigPanelErrorCallout } from "../../ConfigPanelErrorCallout";
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
  const { page, pageSize, setPage, slice } = useClientPagination({
    total: availableModels.length,
    resetKey: selectedRole,
  });
  const [localRoleModels, setLocalRoleModels] = useState<
    Record<string, string[]>
  >({});
  const [isSaving, setIsSaving] = useState(false);
  const [expandedModel, setExpandedModel] = useState<string | null>(null);

  const toggleExpand = (id: string) =>
    setExpandedModel((prev) => (prev === id ? null : id));

  const [saveError, setSaveError] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const descriptionId = useId();

  useEffect(() => {
    if (!roles.find((r) => r.id === selectedRole)) {
      setSelectedRole(roles.length > 0 ? roles[0].id : null);
    }
  }, [roles, selectedRole]);

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
    ? (localRoleModels[selectedRole] ?? roleModelsMap[selectedRole] ?? [])
    : [];

  const toggleModel = (modelId: string) => {
    if (!selectedRole || isSaving) return;
    setLocalRoleModels((prev) => {
      const current = prev[selectedRole] ?? roleModelsMap[selectedRole] ?? [];
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
    if (!selectedRole || isSaving) return;
    setLocalRoleModels((prev) => ({
      ...prev,
      [selectedRole]: availableModels.map((m) => m.id),
    }));
  };

  const handleClearAll = () => {
    if (!selectedRole || isSaving) return;
    setLocalRoleModels((prev) => ({
      ...prev,
      [selectedRole]: [],
    }));
  };

  const handleSave = async () => {
    if (!selectedRole || isSaving) return;
    rootRef.current?.focus({ preventScroll: true });
    setSaveError(null);
    setIsSaving(true);
    try {
      await onUpdate(selectedRole, currentRoleModels);
      setLocalRoleModels((prev) => {
        const next = { ...prev };
        delete next[selectedRole];
        return next;
      });
    } catch (err) {
      setSaveError((err as Error).message || t("agentConfig.saveFailed"));
    } finally {
      setIsSaving(false);
    }
  };

  const selectedRoleData = roles.find((r) => r.id === selectedRole);

  const hasChanges = selectedRole
    ? currentRoleModels.length !== (roleModelsMap[selectedRole] ?? []).length ||
      currentRoleModels.some(
        (id) => !(roleModelsMap[selectedRole] ?? []).includes(id),
      )
    : false;
  if (roles.length === 0)
    return (
      <EmptyState illustration="panel-models" title={t("roles.noRoles")} />
    );

  return (
    <div
      ref={rootRef}
      tabIndex={-1}
      aria-busy={isSaving}
      className="panel-stack focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)]"
    >
      <p className="hidden px-1 text-14 leading-relaxed text-stone-500 sm:block dark:text-stone-400">
        {t("agentConfig.modelsDescription")}
      </p>

      <RoleSelector
        roles={roles}
        selectedRoleId={selectedRole}
        onSelectRole={(id) => {
          setSelectedRole(id);
          setSaveError(null);
        }}
        disabled={isSaving}
      />

      {selectedRole && (
        <>
          <div className="agent-config-list overflow-hidden rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg)] divide-y divide-[var(--glass-border)]">
            {/* Header row */}
            <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 font-serif bg-[var(--glass-bg-subtle)] px-3.5 py-2.5 sm:px-4">
              <h4 className="min-w-0 basis-full text-12 font-medium leading-relaxed text-theme-text-secondary [overflow-wrap:anywhere] sm:flex-1 sm:basis-auto">
                {t("agentConfig.selectModelsForRole", {
                  roleName: selectedRoleData?.name,
                })}
              </h4>
              <div className="flex flex-wrap items-center gap-1 text-12 text-theme-text-secondary">
                <span className="basis-full sm:basis-auto sm:mr-1">
                  {t("agentConfig.selectedModelsCount", {
                    count: currentRoleModels.length,
                    total: availableModels.length,
                  })}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleSelectAll}
                  disabled={isSaving}
                  className="!min-h-11 !text-12"
                >
                  {t("agentConfig.selectAll")}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleClearAll}
                  disabled={isSaving}
                  className="!min-h-11 !text-12"
                >
                  {t("agentConfig.clearAll")}
                </Button>
              </div>
            </div>

            {/* Model rows */}
            <div className="divide-y divide-[var(--glass-border)]">
              {slice(availableModels).map((model) => {
                const isSelected = currentRoleModels.includes(model.id);
                const hasDesc = !!model.description;
                return (
                  <div
                    key={model.id}
                    className={`transition-colors duration-150 motion-reduce:transition-none ${
                      isSelected
                        ? "bg-[var(--glass-bg-subtle)]"
                        : "hover:bg-[var(--glass-bg-hover)]"
                    }`}
                  >
                    <div className="flex min-h-14 items-center gap-3 px-3.5 py-3 sm:px-4 sm:gap-3.5">
                      <label className="flex min-h-11 min-w-0 flex-1 cursor-pointer items-center gap-3 sm:gap-3.5">
                        <Checkbox
                          ariaLabel={model.label}
                          disabled={isSaving}
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
                          <div className="line-clamp-2 text-14 font-medium font-serif text-theme-text [overflow-wrap:anywhere]">
                            {model.label}
                          </div>
                          <div className="text-12 font-mono text-stone-400 dark:text-stone-500 truncate sm:hidden mt-0.5">
                            {model.value}
                          </div>
                        </div>
                        <span className="text-12 font-mono text-stone-400 dark:text-stone-500 truncate max-w-[140px] hidden sm:inline">
                          {model.value}
                        </span>
                      </label>
                      {hasDesc && (
                        <IconButton
                          aria-label={`${t(expandedModel === model.id ? "common.collapse" : "common.expand")} ${model.label}`}
                          aria-expanded={expandedModel === model.id}
                          aria-controls={
                            expandedModel === model.id
                              ? `${descriptionId}-${model.id}`
                              : undefined
                          }
                          onClick={() => toggleExpand(model.id)}
                          className="shrink-0"
                          icon={
                            <ChevronDown
                              size={14}
                              className={`transition-transform duration-200 motion-reduce:transition-none ${
                                expandedModel === model.id ? "rotate-180" : ""
                              }`}
                            />
                          }
                        />
                      )}
                    </div>
                    {expandedModel === model.id && hasDesc && (
                      <div
                        id={`${descriptionId}-${model.id}`}
                        className="px-3.5 pb-3 pl-[3.25rem] pt-0 sm:px-4 sm:pl-[3.75rem] [overflow-wrap:anywhere]"
                      >
                        <p className="text-12 text-stone-500 dark:text-stone-400 leading-relaxed">
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
            <div className="sticky bottom-0 z-10 panel-stack bg-theme-bg py-2">
              {saveError && (
                <ConfigPanelErrorCallout
                  message={saveError}
                  className="max-h-32 overflow-y-auto"
                />
              )}
              <div className="flex justify-end">
                <Button
                  variant="primary"
                  onClick={handleSave}
                  loading={isSaving}
                  leftIcon={<Save size={16} />}
                  className="!min-h-11"
                >
                  {t("common.save")}
                </Button>
              </div>
            </div>
          )}
          <div className="panel-pagination empty:hidden">
            <Pagination
              page={page}
              pageSize={pageSize}
              total={availableModels.length}
              onChange={setPage}
            />
          </div>
        </>
      )}
    </div>
  );
}
