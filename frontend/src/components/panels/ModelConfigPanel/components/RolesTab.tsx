/**
 * Roles tab content for model permission management
 */
import { useState, useEffect } from "react";
import { ChevronDown, Shield, Sparkles, Save } from "lucide-react";
import { useTranslation } from "react-i18next";
import { LoadingSpinner } from "../../../common/LoadingSpinner";
import { Toggle } from "./Toggle";
import type { ModelConfig, Role } from "../../../../types";

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

  const handleSave = () => {
    if (!selectedRole) return;
    try {
      onUpdate(selectedRole, localRoleModels[selectedRole] || []);
    } catch (err) {
      console.error("Failed to save role models:", err);
    }
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
      <p
        className="text-sm px-1 hidden sm:block"
        style={{ color: "var(--theme-text-secondary)" }}
      >
        {t("modelConfig.rolesDescription")}
      </p>

      {/* Role selector - Mobile dropdown */}
      <div className="sm:hidden">
        <div className="relative">
          <button
            onClick={() => setRoleDropdownOpen(!roleDropdownOpen)}
            className="flex w-full items-center justify-between rounded-xl px-4 py-3.5 text-sm font-medium transition-colors"
            style={{
              border: "1px solid var(--theme-border)",
              background: "var(--theme-bg-card)",
              color: "var(--theme-text)",
            }}
          >
            <span className="flex items-center gap-2">
              <Shield size={16} style={{ color: "var(--theme-primary)" }} />
              {selectedRoleData?.name || t("modelConfig.selectRole")}
            </span>
            <ChevronDown
              size={18}
              className="transition-transform"
              style={{ color: "var(--theme-text-secondary)" }}
            />
          </button>

          {roleDropdownOpen && (
            <div
              className="absolute z-10 mt-2 w-full rounded-xl shadow-xl overflow-hidden"
              style={{
                border: "1px solid var(--theme-border)",
                background: "var(--theme-bg-card)",
              }}
            >
              {roles.map((role) => (
                <button
                  key={role.id}
                  onClick={() => {
                    setSelectedRole(role.id);
                    setRoleDropdownOpen(false);
                  }}
                  className="flex w-full items-center justify-between px-4 py-3.5 text-sm first:rounded-t-xl last:rounded-b-xl transition-colors"
                  style={
                    selectedRole === role.id
                      ? {
                          background: "var(--theme-primary-light)",
                          color: "var(--theme-text)",
                        }
                      : { color: "var(--theme-text-secondary)" }
                  }
                >
                  <span>{role.name}</span>
                  {selectedRole === role.id && (
                    <Sparkles
                      size={16}
                      style={{ color: "var(--theme-primary)" }}
                    />
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Desktop role tabs */}
      <div
        className="hidden sm:flex gap-1 p-1.5 rounded-xl overflow-x-auto"
        style={{ background: "var(--theme-bg)" }}
      >
        {roles.map((role) => (
          <button
            key={role.id}
            onClick={() => setSelectedRole(role.id)}
            className="flex-shrink-0 px-5 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 flex items-center gap-2"
            style={
              selectedRole === role.id
                ? {
                    background: "var(--theme-bg-card)",
                    color: "var(--theme-text)",
                    boxShadow: "0 2px 8px rgba(0,0,0,0.1)",
                  }
                : { color: "var(--theme-text-secondary)" }
            }
          >
            <Shield size={14} style={{ color: "var(--theme-primary)" }} />
            {role.name}
          </button>
        ))}
      </div>

      {selectedRole && (
        <>
          <div
            className="rounded-2xl p-5 space-y-5"
            style={{
              background: "var(--theme-bg-card)",
              border: "1px solid var(--theme-border)",
            }}
          >
            <div className="flex items-center gap-2">
              <Shield size={18} style={{ color: "var(--theme-primary)" }} />
              <h4
                className="text-sm font-semibold"
                style={{ color: "var(--theme-text)" }}
              >
                {t("modelConfig.selectModelsForRole", {
                  roleName: selectedRoleData?.name,
                })}
              </h4>
              <span
                className="ml-auto text-xs px-2 py-0.5 rounded-full"
                style={{
                  background: "var(--theme-primary-light)",
                  color: "var(--theme-primary)",
                }}
              >
                {currentRoleModels.length} selected
              </span>
            </div>

            {/* Grouped models */}
            {Object.entries(groupedModels).map(([provider, models]) => (
              <div key={provider} className="space-y-3">
                <div
                  className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider px-1"
                  style={{ color: "var(--theme-text-secondary)" }}
                >
                  {provider}
                </div>
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {models.map((model) => {
                    const isEnabled = currentRoleModels.includes(model.value);
                    return (
                      <label
                        key={model.value}
                        className={`flex items-center gap-3 rounded-xl p-3 cursor-pointer transition-all duration-200 ${
                          isEnabled ? "shadow-sm" : ""
                        }`}
                        style={
                          isEnabled
                            ? {
                                background: "var(--theme-primary-light)",
                                boxShadow: "0 0 0 1px var(--theme-primary)",
                              }
                            : {
                                background: "var(--theme-bg-card)",
                                border: "1px solid var(--theme-border)",
                              }
                        }
                      >
                        <Toggle
                          checked={isEnabled}
                          onChange={() => toggleModel(model.value)}
                        />
                        <div className="min-w-0 flex-1">
                          <div
                            className="text-sm font-medium truncate"
                            style={{ color: "var(--theme-text)" }}
                          >
                            {model.label}
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
            ))}

            {ungrouped.length > 0 && Object.keys(groupedModels).length > 0 && (
              <div
                className="border-t"
                style={{ borderColor: "var(--theme-border)" }}
              />
            )}

            {ungrouped.length > 0 && (
              <div className="space-y-3">
                <div
                  className="text-xs font-semibold uppercase tracking-wider px-1"
                  style={{ color: "var(--theme-text-secondary)" }}
                >
                  Other Models
                </div>
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {ungrouped.map((model) => {
                    const isEnabled = currentRoleModels.includes(model.value);
                    return (
                      <label
                        key={model.value}
                        className={`flex items-center gap-3 rounded-xl p-3 cursor-pointer transition-all duration-200 ${
                          isEnabled ? "shadow-sm" : ""
                        }`}
                        style={
                          isEnabled
                            ? {
                                background: "var(--theme-primary-light)",
                                boxShadow: "0 0 0 1px var(--theme-primary)",
                              }
                            : {
                                background: "var(--theme-bg-card)",
                                border: "1px solid var(--theme-border)",
                              }
                        }
                      >
                        <Toggle
                          checked={isEnabled}
                          onChange={() => toggleModel(model.value)}
                        />
                        <div className="min-w-0 flex-1">
                          <div
                            className="text-sm font-medium truncate"
                            style={{ color: "var(--theme-text)" }}
                          >
                            {model.label}
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

            {flatModels.length === 0 && (
              <div className="text-center py-12">
                <Sparkles
                  size={40}
                  className="mx-auto mb-4 opacity-30"
                  style={{ color: "var(--theme-primary)" }}
                />
                <p
                  className="text-sm"
                  style={{ color: "var(--theme-text-secondary)" }}
                >
                  {t("modelConfig.noModels")}
                </p>
              </div>
            )}
          </div>

          {hasChanges && (
            <div className="flex justify-end pt-2">
              <button
                onClick={handleSave}
                className="flex items-center gap-2 px-5 py-2.5 text-sm font-medium rounded-xl text-white transition-all duration-200 hover:scale-105 active:scale-95"
                style={{
                  background: "var(--theme-primary)",
                  boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
                }}
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

export default RolesTab;
