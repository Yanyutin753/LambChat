import { useState, useEffect } from "react";
import { Save } from "lucide-react";
import { useTranslation } from "react-i18next";
import i18n from "../../../../i18n";
import { AgentIcon } from "../../../agent/AgentIcon";
import { AgentPanelSkeleton } from "../../../skeletons";
import { Button } from "../../../common";
import { Checkbox } from "../../../common/Checkbox";
import {
  resolveAgentDescription,
  resolveAgentDisplayName,
} from "../../../agent/agentCatalog";
import { RoleSelector } from "../shared/RoleSelector";
import { groupAgentsByPluginCategory } from "../agentCategoryGroups";
import type { CoreAgentCategoryContribution } from "../../../../extensions";
import type { Role, AgentInfo } from "../../../../types";

interface RolesAgentTabProps {
  roles: Role[];
  roleAgentsMap: Record<string, string[]>;
  availableAgents: AgentInfo[];
  onUpdate: (roleId: string, agentIds: string[]) => Promise<void>;
  isLoading: boolean;
  agentCategories?: readonly CoreAgentCategoryContribution[];
}

export function RolesAgentTab({
  roles,
  roleAgentsMap,
  availableAgents,
  onUpdate,
  isLoading,
  agentCategories = [],
}: RolesAgentTabProps) {
  const { t } = useTranslation();
  const [selectedRole, setSelectedRole] = useState<string | null>(
    roles.length > 0 ? roles[0].id : null,
  );
  const [localRoleAgents, setLocalRoleAgents] =
    useState<Record<string, string[]>>(roleAgentsMap);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    setLocalRoleAgents(roleAgentsMap);
  }, [roleAgentsMap]);

  // Reset selectedRole if it no longer exists in the roles list
  useEffect(() => {
    if (selectedRole && !roles.find((r) => r.id === selectedRole)) {
      setSelectedRole(roles.length > 0 ? roles[0].id : null);
    }
  }, [roles, selectedRole]);

  if (isLoading) {
    return <AgentPanelSkeleton />;
  }

  const currentRoleAgents = selectedRole
    ? localRoleAgents[selectedRole] || []
    : [];

  const toggleAgent = (agentId: string) => {
    if (!selectedRole) return;
    setLocalRoleAgents((prev) => {
      const current = prev[selectedRole] || [];
      if (current.includes(agentId)) {
        return {
          ...prev,
          [selectedRole]: current.filter((id) => id !== agentId),
        };
      }
      return { ...prev, [selectedRole]: [...current, agentId] };
    });
  };

  const handleSave = async () => {
    if (!selectedRole) return;
    setIsSaving(true);
    try {
      await onUpdate(selectedRole, localRoleAgents[selectedRole] || []);
    } catch (err) {
      console.error("Failed to save role agents:", err);
    } finally {
      setIsSaving(false);
    }
  };

  const selectedRoleData = roles.find((r) => r.id === selectedRole);
  const hasChanges = selectedRole
    ? JSON.stringify(localRoleAgents[selectedRole]) !==
      JSON.stringify(roleAgentsMap[selectedRole])
    : false;

  return (
    <div className="space-y-4">
      <p className="hidden px-1 text-sm leading-relaxed text-theme-text-secondary sm:block">
        {t("agentConfig.rolesDescription")}
      </p>

      <RoleSelector
        roles={roles}
        selectedRoleId={selectedRole}
        onSelectRole={setSelectedRole}
      />

      {selectedRole && (
        <>
          <div className="glass-card overflow-hidden rounded-xl">
            <div className="bg-[var(--glass-bg-subtle)] px-4 py-2.5">
              <h4 className="truncate text-xs font-medium uppercase tracking-wider text-theme-text-secondary">
                {t("agentConfig.selectAgentsForRole", {
                  roleName: selectedRoleData?.name,
                })}
              </h4>
            </div>
            <div className="divide-y divide-[var(--glass-border)]">
            {groupAgentsByPluginCategory(availableAgents, agentCategories).map((group) => (
              <section key={group.id}>
                <div className="flex items-center gap-2 bg-[var(--glass-bg-subtle)] px-4 py-2 text-xs font-medium uppercase tracking-wider text-theme-text-tertiary">
                  <AgentIcon icon={group.icon} size={14} />
                  <span>{t(group.label, group.label)}</span>
                </div>
                <div className="divide-y divide-[var(--glass-border)]">
            {group.agents.map((agent, index) => {
              const isSelected = currentRoleAgents.includes(agent.id);
              const displayName = resolveAgentDisplayName(
                agent,
                i18n.language,
                t,
              );
              const displayDescription = resolveAgentDescription(
                agent,
                i18n.language,
                t,
              );
              return (
                <label
                  key={agent.id}
                  className={`flex cursor-pointer items-center gap-3.5 px-4 py-3.5 transition-colors duration-150 ${
                    isSelected
                      ? "bg-[var(--glass-bg-subtle)]"
                      : "hover:bg-[var(--glass-bg-hover)]"
                  }`}
                  style={{ animationDelay: `${index * 30}ms` }}
                >
                  <Checkbox
                    checked={isSelected}
                    onChange={() => toggleAgent(agent.id)}
                    size="sm"
                  />
                  <div className="flex size-9 flex-shrink-0 items-center justify-center overflow-hidden rounded-xl bg-[var(--glass-bg-subtle)] text-theme-text-secondary ring-1 ring-[var(--glass-border)]">
                    <AgentIcon icon={agent.icon || "Bot"} size={16} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium text-theme-text">
                      {displayName}
                    </div>
                    <div className="mt-0.5 hidden truncate text-xs text-theme-text-secondary sm:block">
                      {displayDescription}
                    </div>
                  </div>
                </label>
              );
            })}
                </div>
              </section>
            ))}
            </div>
          </div>

          {hasChanges && (
            <div className="glass-divider mt-4 flex items-center justify-between pt-4">
              <span className="flex items-center gap-1.5 text-xs text-theme-text-tertiary">
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse" />
                {currentRoleAgents.length} / {availableAgents.length}
              </span>
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
