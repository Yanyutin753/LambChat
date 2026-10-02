import { useState, useEffect, useRef } from "react";
import { Save } from "lucide-react";
import { useTranslation } from "react-i18next";
import i18n from "../../../../i18n";
import { AgentIcon } from "../../../agent/AgentIcon";
import { AgentPanelSkeleton } from "../../../skeletons";
import { Button, EmptyState } from "../../../common";
import { Checkbox } from "../../../common/Checkbox";
import {
  resolveAgentDescription,
  resolveAgentDisplayName,
} from "../../../agent/agentCatalog";
import { ConfigPanelErrorCallout } from "../../ConfigPanelErrorCallout";
import { RoleSelector } from "../shared/RoleSelector";
import type { Role, AgentInfo } from "../../../../types";

interface RolesAgentTabProps {
  roles: Role[];
  roleAgentsMap: Record<string, string[]>;
  availableAgents: AgentInfo[];
  onUpdate: (roleId: string, agentIds: string[]) => Promise<void>;
  isLoading: boolean;
}

export function RolesAgentTab({
  roles,
  roleAgentsMap,
  availableAgents,
  onUpdate,
  isLoading,
}: RolesAgentTabProps) {
  const { t } = useTranslation();
  const [selectedRole, setSelectedRole] = useState<string | null>(
    roles.length > 0 ? roles[0].id : null,
  );
  const [localRoleAgents, setLocalRoleAgents] = useState<
    Record<string, string[]>
  >({});
  const [isSaving, setIsSaving] = useState(false);

  const [saveError, setSaveError] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  // Reset selectedRole if it no longer exists in the roles list
  useEffect(() => {
    if (!roles.find((r) => r.id === selectedRole)) {
      setSelectedRole(roles.length > 0 ? roles[0].id : null);
    }
  }, [roles, selectedRole]);

  if (isLoading) {
    return <AgentPanelSkeleton />;
  }

  const currentRoleAgents = selectedRole
    ? (localRoleAgents[selectedRole] ?? roleAgentsMap[selectedRole] ?? [])
    : [];

  const toggleAgent = (agentId: string) => {
    if (!selectedRole || isSaving) return;
    setLocalRoleAgents((prev) => {
      const current = prev[selectedRole] ?? roleAgentsMap[selectedRole] ?? [];
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
    if (!selectedRole || isSaving) return;
    rootRef.current?.focus({ preventScroll: true });
    setSaveError(null);
    setIsSaving(true);
    try {
      await onUpdate(selectedRole, currentRoleAgents);
      setLocalRoleAgents((prev) => {
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
    ? currentRoleAgents.length !== (roleAgentsMap[selectedRole] ?? []).length ||
      currentRoleAgents.some(
        (id) => !(roleAgentsMap[selectedRole] ?? []).includes(id),
      )
    : false;

  if (roles.length === 0)
    return (
      <EmptyState illustration="panel-agents" title={t("roles.noRoles")} />
    );

  return (
    <div
      ref={rootRef}
      tabIndex={-1}
      aria-busy={isSaving}
      className="panel-stack focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)]"
    >
      {saveError && <ConfigPanelErrorCallout message={saveError} />}
      <p className="hidden px-1 text-14 leading-relaxed text-theme-text-secondary sm:block">
        {t("agentConfig.rolesDescription")}
      </p>

      <RoleSelector
        roles={roles}
        selectedRoleId={selectedRole}
        onSelectRole={(roleId) => {
          setSelectedRole(roleId);
          setSaveError(null);
        }}
        disabled={isSaving}
      />

      {selectedRole && (
        <>
          <div className="glass-card divide-y divide-[var(--glass-border)] overflow-hidden rounded-xl">
            <div className="bg-[var(--glass-bg-subtle)] px-4 py-2.5 font-serif">
              <h4 className="text-12 font-medium leading-relaxed text-theme-text-secondary [overflow-wrap:anywhere]">
                {t("agentConfig.selectAgentsForRole", {
                  roleName: selectedRoleData?.name,
                })}
              </h4>
            </div>
            {availableAgents.length === 0 && (
              <EmptyState title={t("agentConfig.noAvailableAgents")} />
            )}
            {availableAgents.map((agent) => {
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
                  className={`flex min-h-11 cursor-pointer items-center gap-3.5 px-4 py-3.5 transition-colors duration-150 motion-reduce:transition-none ${
                    isSelected
                      ? "bg-[var(--glass-bg-subtle)]"
                      : "hover:bg-[var(--glass-bg-hover)]"
                  }`}
                >
                  <Checkbox
                    ariaLabel={displayName}
                    disabled={isSaving}
                    checked={isSelected}
                    onChange={() => toggleAgent(agent.id)}
                    size="sm"
                  />
                  <div className="flex size-9 flex-shrink-0 items-center justify-center overflow-hidden rounded-xl bg-[var(--glass-bg-subtle)] text-theme-text-secondary ring-1 ring-[var(--glass-border)]">
                    <AgentIcon icon={agent.icon || "Bot"} size={16} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-14 font-medium font-serif text-theme-text">
                      {displayName}
                    </div>
                    <div className="mt-0.5 hidden truncate text-12 text-theme-text-secondary sm:block">
                      {displayDescription}
                    </div>
                  </div>
                </label>
              );
            })}
          </div>

          {hasChanges && (
            <div className="glass-divider mt-4 flex items-center justify-between pt-4">
              <span className="flex items-center gap-1.5 text-12 text-theme-text-tertiary">
                {currentRoleAgents.length} / {availableAgents.length}
              </span>
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
          )}
        </>
      )}
    </div>
  );
}
