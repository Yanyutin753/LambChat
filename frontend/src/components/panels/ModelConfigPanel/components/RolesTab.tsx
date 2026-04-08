/**
 * Roles tab content for model permission management
 */
import { useState, useEffect } from "react";
import {
  ChevronDown,
  Shield,
  Sparkles,
  Save,
  Users,
  RotateCcw,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { LoadingSpinner } from "../../../common/LoadingSpinner";
import { Toggle } from "./Toggle";
import { ProviderBadge } from "./ProviderBadge";
import type { ModelConfig, Role } from "../../../../types";
import { getProviderMeta } from "../../../../types/model";

function RolesTab({
  roles,
  roleModelsMap,
  flatModels,
  onUpdate,
  isLoading,
}: {
  roles: Role[];
  roleModelsMap: Record<string, string[]>;
  flatModels: ModelConfig[];
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

  useEffect(() => {
    if (!selectedRole && roles.length > 0) {
      setSelectedRole(roles[0].id);
    }
  }, [roles, selectedRole]);

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
  const hasModels = flatModels.length > 0;

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

  const handleSave = () => {
    if (!selectedRole) return;
    try {
      onUpdate(selectedRole, localRoleModels[selectedRole] || []);
    } catch (err) {
      console.error("Failed to save role models:", err);
    }
  };

  const handleReset = () => {
    if (!selectedRole) return;
    setLocalRoleModels((prev) => ({
      ...prev,
      [selectedRole]: roleModelsMap[selectedRole] || [],
    }));
  };

  const selectedRoleData = roles.find((r) => r.id === selectedRole);
  const hasChanges = selectedRole
    ? JSON.stringify(localRoleModels[selectedRole]) !==
      JSON.stringify(roleModelsMap[selectedRole])
    : false;

  // Group models by provider for display
  const groupedModels: Record<string, ModelConfig[]> = {};
  const ungrouped: ModelConfig[] = [];
  for (const m of flatModels) {
    if (m.provider) {
      if (!groupedModels[m.provider]) groupedModels[m.provider] = [];
      groupedModels[m.provider].push(m);
    } else {
      ungrouped.push(m);
    }
  }

  return (
    <div className="space-y-4">
      <div className="model-config-subtle-card rounded-2xl px-4 py-3 text-sm text-[var(--theme-text-secondary)]">
        {t("modelConfig.rolesDescription")}
      </div>

      {/* Role selector */}
      <div>
        <div className="relative">
          <button
            onClick={() => setRoleDropdownOpen(!roleDropdownOpen)}
            className="model-config-role-card flex w-full items-center justify-between rounded-2xl px-4 py-3 text-sm font-medium text-[var(--theme-text)] transition-colors"
          >
            <span className="flex items-center gap-2">
              <Users size={15} style={{ color: "var(--theme-primary)" }} />
              {selectedRoleData?.name || t("modelConfig.selectRole")}
            </span>
            <ChevronDown
              size={16}
              className="transition-transform"
              style={{ color: "var(--theme-text-secondary)" }}
            />
          </button>

          {roleDropdownOpen && (
            <div className="model-config-role-card model-config-dropdown-menu absolute z-10 mt-1.5 w-full overflow-hidden rounded-2xl shadow-lg">
              {roles.map((role) => (
                <button
                  key={role.id}
                  onClick={() => {
                    setSelectedRole(role.id);
                    setRoleDropdownOpen(false);
                  }}
                  className={`model-config-role-card-option flex w-full items-center justify-between px-4 py-3 text-sm first:rounded-t-xl last:rounded-b-xl ${selectedRole === role.id ? "is-active" : ""}`}
                >
                  <span className="flex items-center gap-2">
                    <Users size={14} style={{ color: "var(--theme-text-secondary)" }} />
                    {role.name}
                  </span>
                  {selectedRole === role.id && (
                    <Shield
                      size={14}
                      style={{ color: "var(--theme-primary)" }}
                    />
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {selectedRole && (
        <>
          <div
            className={`model-config-role-card rounded-3xl p-4 sm:p-5 ${
              hasModels ? "space-y-5" : "space-y-4"
            }`}
          >
            {/* Header */}
            <div className="flex items-center gap-3">
              <div
                className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
                style={{
                  background: "var(--theme-primary-light)",
                }}
              >
                <Shield size={18} style={{ color: "var(--theme-primary)" }} />
              </div>
              <div className="flex-1 min-w-0">
                <h4
                  className="text-sm font-semibold"
                  style={{ color: "var(--theme-text)" }}
                >
                  {t("modelConfig.selectModelsForRole", {
                    roleName: selectedRoleData?.name,
                  })}
                </h4>
              </div>
              <span
                className="text-xs px-2.5 py-1 rounded-full font-medium"
                style={{
                  background: "var(--theme-primary-light)",
                  color: "var(--theme-primary)",
                }}
              >
                {currentRoleModels.length} selected
              </span>
            </div>

            {/* Grouped models */}
            {Object.entries(groupedModels).map(([provider, models]) => {
              const meta = getProviderMeta(provider);
              const brandColor = meta?.color || "#78716c";
              return (
                <div key={provider} className="space-y-2.5">
                  <div className="flex items-center gap-2.5 px-0.5">
                    <ProviderBadge provider={provider} size="sm" />
                    <span
                      className="text-xs font-semibold uppercase tracking-wider"
                      style={{ color: "var(--theme-text-secondary)" }}
                    >
                      {meta?.display_name || provider}
                    </span>
                    <span
                      className="text-[11px] px-1.5 py-0.5 rounded-full"
                      style={{
                        background: `${brandColor}12`,
                        color: brandColor,
                      }}
                    >
                      {models.length}
                    </span>
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                    {models.map((model) => {
                      const modelValue = model.value || model.id || "";
                      const isEnabled = currentRoleModels.includes(modelValue);
                      return (
                        <label
                          key={modelValue}
                          className="model-config-model-option flex cursor-pointer items-center gap-3 rounded-2xl p-3"
                          style={
                            isEnabled
                              ? {
                                  background: `${brandColor}08`,
                                  border: `1px solid ${brandColor}30`,
                                }
                              : {
                                  background: "var(--theme-bg)",
                                  border: "1px solid var(--theme-border)",
                                }
                          }
                        >
                          <Toggle
                            checked={isEnabled}
                            onChange={() => toggleModel(modelValue)}
                            color={brandColor}
                          />
                          <div className="min-w-0 flex-1">
                            <div
                              className="text-sm font-medium truncate"
                              style={{ color: "var(--theme-text)" }}
                            >
                              {model.label || model.name || modelValue}
                            </div>
                            {model.description && (
                              <div
                                className="text-xs truncate mt-0.5"
                                style={{ color: "var(--theme-text-secondary)" }}
                              >
                                {model.description}
                              </div>
                            )}
                          </div>
                        </label>
                      );
                    })}
                  </div>
                </div>
              );
            })}

            {ungrouped.length > 0 && Object.keys(groupedModels).length > 0 && (
              <div
                className="border-t"
                style={{ borderColor: "var(--theme-border)" }}
              />
            )}

            {ungrouped.length > 0 && (
              <div className="space-y-2.5">
                <div
                  className="text-xs font-semibold uppercase tracking-wider px-0.5"
                  style={{ color: "var(--theme-text-secondary)" }}
                >
                  Other Models
                </div>
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {ungrouped.map((model) => {
                    const modelValue = model.value || model.id || "";
                    const isEnabled = currentRoleModels.includes(modelValue);
                    return (
                      <label
                        key={modelValue}
                        className="model-config-model-option flex cursor-pointer items-center gap-3 rounded-2xl p-3"
                        style={
                          isEnabled
                            ? {
                                background: "var(--theme-primary-light)",
                                border: "1px solid var(--theme-primary)",
                              }
                            : {
                                background: "var(--theme-bg)",
                                border: "1px solid var(--theme-border)",
                              }
                        }
                      >
                        <Toggle
                          checked={isEnabled}
                          onChange={() => toggleModel(modelValue)}
                        />
                        <div className="min-w-0 flex-1">
                          <div
                            className="text-sm font-medium truncate"
                            style={{ color: "var(--theme-text)" }}
                          >
                            {model.label || model.name || modelValue}
                          </div>
                          {model.description && (
                            <div
                              className="text-xs truncate mt-0.5"
                              style={{ color: "var(--theme-text-secondary)" }}
                            >
                              {model.description}
                            </div>
                          )}
                        </div>
                      </label>
                    );
                  })}
                </div>
              </div>
            )}

            {!hasModels && (
              <div
                className="rounded-2xl px-4 py-5 sm:px-5"
                style={{
                  background:
                    "linear-gradient(180deg, color-mix(in srgb, var(--theme-primary-light) 52%, transparent), color-mix(in srgb, var(--theme-bg) 78%, transparent))",
                  border:
                    "1px solid color-mix(in srgb, var(--theme-primary) 10%, var(--theme-border))",
                }}
              >
                <div className="flex items-start gap-3">
                  <div
                    className="flex size-9 flex-shrink-0 items-center justify-center rounded-xl"
                    style={{
                      background:
                        "color-mix(in srgb, var(--theme-primary-light) 78%, var(--theme-bg) 22%)",
                      color: "var(--theme-primary)",
                    }}
                  >
                    <Sparkles size={16} />
                  </div>
                  <div className="min-w-0">
                    <p
                      className="text-sm font-medium"
                      style={{ color: "var(--theme-text)" }}
                    >
                      {t("modelConfig.noModelsTitle")}
                    </p>
                    <p
                      className="mt-1 text-sm leading-6"
                      style={{ color: "var(--theme-text-secondary)" }}
                    >
                      {t("modelConfig.noModels")}
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Save bar */}
          {hasChanges && (
            <div
              className="model-config-savebar flex flex-col gap-3 rounded-2xl px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="flex items-center gap-2">
                <div
                  className="w-2 h-2 rounded-full animate-pulse"
                  style={{ background: "var(--theme-primary)" }}
                />
                <span
                  className="text-xs font-medium"
                  style={{ color: "var(--theme-primary)" }}
                >
                  {t("modelConfig.unsavedChanges")}
                </span>
              </div>
              <div className="flex items-center gap-2 self-end sm:self-auto">
                <button
                  onClick={handleReset}
                  className="btn-secondary px-3 py-1.5 text-xs"
                >
                  <RotateCcw size={12} className="inline mr-1" />
                  {t("common.cancel")}
                </button>
                <button
                  onClick={handleSave}
                  className="btn-primary px-4 py-1.5 text-xs"
                >
                  <Save size={13} />
                  {t("common.save")}
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default RolesTab;
