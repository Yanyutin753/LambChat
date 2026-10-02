import { useId, useRef, useState } from "react";
import { Bot, ChevronDown, Cpu, Star, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import i18n from "../../i18n";
import type { TeamMember } from "../../types/team";
import type { ModelOption } from "../../services/api/model";
import type { AgentInfo } from "../../types/agent";
import { resolveAgentDisplayName } from "../agent/agentCatalog";
import {
  PersonaAvatarIcon,
  PersonaAvatarImage,
} from "../persona/PersonaAvatarIcon";
import {
  getEmojiAvatarUrl,
  isEmojiAvatar,
  isPersonaImageAvatar,
} from "../persona/personaAvatar";
import { Select, Textarea, IconButton } from "../common/ui";
import type { SelectOption } from "../common/ui";
import { Tooltip } from "../common/Tooltip";

interface TeamMemberCardProps {
  member: TeamMember;
  disabled?: boolean;
  isDefault: boolean;
  onRemove: () => void;
  onSetDefault: () => void;
  onToggleEnabled: () => void;
  onInstructionsChange: (text: string) => void;
  modelsUnavailable?: boolean;
  agentsUnavailable?: boolean;
  availableModels?: ModelOption[];
  onModelChange?: (modelId: string | null) => void;
  availableAgents?: AgentInfo[];
  onAgentChange?: (agentId: string | null) => void;
}

export function TeamMemberCard({
  member,
  disabled = false,
  isDefault,
  onRemove,
  onSetDefault,
  onToggleEnabled,
  onInstructionsChange,
  modelsUnavailable = false,
  agentsUnavailable = false,
  availableModels = [],
  onModelChange,
  availableAgents = [],
  onAgentChange,
}: TeamMemberCardProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const settingsId = useId();
  const summaryRef = useRef<HTMLButtonElement>(null);
  const roleName = member.role_name || t("team.unnamedRole");

  const selectedModel = member.model_id
    ? availableModels.find((model) => model.id === member.model_id)
    : null;
  const modelLabel = member.model_id
    ? selectedModel?.label || selectedModel?.value || member.model_id
    : t("team.followSessionModel", "跟随会话模型");
  const selectedAgent = member.agent_id
    ? availableAgents.find((agent) => agent.id === member.agent_id)
    : null;
  const agentLabel = member.agent_id
    ? selectedAgent
      ? resolveAgentDisplayName(selectedAgent, i18n.language, t)
      : member.agent_id
    : t("team.followTeamMode", "跟随团队模式");

  const agentOptions: SelectOption[] = [
    { value: "", label: t("team.followTeamMode", "跟随团队模式") },
    ...availableAgents.map((agent) => ({
      value: agent.id,
      label: (
        <span className="font-serif">
          {resolveAgentDisplayName(agent, i18n.language, t) || agent.id}
        </span>
      ),
    })),
  ];

  const modelOptions: SelectOption[] = [
    { value: "", label: t("team.followSessionModel", "跟随会话模型") },
    ...availableModels.map((model) => ({
      value: model.id,
      label: <span className="font-serif">{model.label || model.value}</span>,
    })),
  ];

  return (
    <div
      className={`team-member-card list-item-card ${
        expanded ? "list-item-card--expanded" : ""
      } ${member.enabled ? "" : "list-item-card--disabled"}`}
    >
      <div className="list-item-card__body">
        {/* Main row: avatar + name + tags + actions */}
        <div className="list-item-card__top">
          <button
            ref={summaryRef}
            type="button"
            disabled={disabled}
            className="team-member-card__summary"
            aria-label={`${t(expanded ? "common.collapse" : "common.expand")} ${roleName}`}
            aria-expanded={expanded}
            aria-controls={settingsId}
            onClick={() => setExpanded(!expanded)}
          >
            <span className="team-member-card__avatar-btn">
              {isPersonaImageAvatar(member.role_avatar) ||
              isEmojiAvatar(member.role_avatar) ? (
                <span className="team-member-card__avatar">
                  <PersonaAvatarImage
                    avatar={
                      isEmojiAvatar(member.role_avatar)
                        ? getEmojiAvatarUrl(member.role_avatar)
                        : member.role_avatar
                    }
                    alt=""
                    className="team-member-card__avatar-img"
                  />
                </span>
              ) : (
                <span className="team-member-card__avatar team-member-card__avatar--icon">
                  <PersonaAvatarIcon
                    avatar={member.role_avatar}
                    primaryTag={member.role_tags[0]}
                    size={18}
                    className="text-[var(--theme-primary)]"
                  />
                </span>
              )}
            </span>

            <span className="list-item-card__identity">
              <span className="team-member-card__identity-header">
                <span className="list-item-card__name font-serif">
                  {roleName}
                </span>
                {member.role_tags.length > 0 && (
                  <span className="team-member-card__tags">
                    {member.role_tags.slice(0, 3).map((tag) => (
                      <span key={tag} className="team-member-card__tag">
                        {tag}
                      </span>
                    ))}
                  </span>
                )}
              </span>
              <span className="team-member-card__meta-row">
                <span className="team-member-card__model" title={agentLabel}>
                  <Bot size={11} />
                  <span className="font-serif">{agentLabel}</span>
                </span>
                <span className="team-member-card__model" title={modelLabel}>
                  <Cpu size={11} />
                  <span className="font-serif">{modelLabel}</span>
                </span>
              </span>
            </span>
            <ChevronDown
              size={14}
              aria-hidden="true"
              className={`team-member-card__expand-icon ${expanded ? "team-member-card__expand-icon--open" : ""}`}
            />
          </button>

          {/* Inline actions */}
          <div className="list-item-card__actions">
            <Tooltip
              content={isDefault ? t("team.defaultRole") : t("team.setDefault")}
            >
              <IconButton
                disabled={disabled}
                aria-label={`${t(isDefault ? "team.defaultRole" : "team.setDefault")} ${roleName}`}
                aria-pressed={isDefault}
                onClick={onSetDefault}
                icon={
                  <Star size={14} fill={isDefault ? "currentColor" : "none"} />
                }
                variant="ghost"
                size="sm"
                className={
                  isDefault
                    ? "team-member-card__action-btn team-member-card__action-btn--active"
                    : "team-member-card__action-btn"
                }
              />
            </Tooltip>
            <Tooltip content={t("team.remove")}>
              <IconButton
                disabled={disabled}
                aria-label={`${t("team.remove")} ${roleName}`}
                onClick={onRemove}
                icon={<Trash2 size={14} />}
                variant="ghost"
                size="sm"
                className="team-member-card__action-btn team-member-card__action-btn--danger"
              />
            </Tooltip>
            {/* Toggle */}
            <button
              disabled={disabled}
              onClick={onToggleEnabled}
              className="team-member-card__toggle-button flex size-11 shrink-0 items-center justify-center rounded-md sm:h-5 sm:w-9"
              aria-label={`${t(member.enabled ? "team.disableRole" : "team.enableRole")} ${roleName}`}
              title={
                member.enabled ? t("team.disableRole") : t("team.enableRole")
              }
              type="button"
              role="switch"
              aria-checked={member.enabled}
            >
              <span
                aria-hidden="true"
                className={`team-toggle ${member.enabled ? "team-toggle--on" : ""}`}
              />
            </button>
          </div>
        </div>

        {/* Collapsible instructions with smooth animation */}
        <div
          id={settingsId}
          inert={!expanded}
          aria-hidden={!expanded}
          onKeyDown={(event) => {
            if (event.key !== "Escape") return;
            event.stopPropagation();
            if (event.nativeEvent.isComposing || event.keyCode === 229) return;
            event.preventDefault();
            setExpanded(false);
            summaryRef.current?.focus();
          }}
          className={`team-member-card__collapse ${
            expanded ? "team-member-card__collapse--open" : ""
          }`}
        >
          <div className="list-item-card__instructions">
            <div className="team-member-card__instructions-divider" />
            <div className="team-member-card__field">
              <label className="ppe-label">
                <Bot size={13} className="ppe-label-icon" />
                {t("team.memberMode", "成员模式")}
              </label>
              <Select
                ariaLabel={`${t("team.memberMode")} ${roleName}`}
                value={member.agent_id ?? ""}
                onChange={(v) => onAgentChange?.(v || null)}
                options={agentOptions}
                disabled={
                  disabled || agentsUnavailable || !expanded || !onAgentChange
                }
                placeholder={agentLabel}
                triggerClassName="team-member-card__select-trigger"
              />
            </div>
            <div className="team-member-card__field">
              <label className="ppe-label">
                <Cpu size={13} className="ppe-label-icon" />
                {t("team.memberModel", "成员模型")}
              </label>
              <Select
                ariaLabel={`${t("team.memberModel")} ${roleName}`}
                value={member.model_id ?? ""}
                onChange={(v) => onModelChange?.(v || null)}
                options={modelOptions}
                disabled={
                  disabled || modelsUnavailable || !expanded || !onModelChange
                }
                placeholder={modelLabel}
                triggerClassName="team-member-card__select-trigger"
              />
            </div>
            <div className="team-member-card__field">
              <label className="ppe-label">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="13"
                  height="13"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="ppe-label-icon"
                >
                  <path d="M12 20h9" />
                  <path d="M16.376 3.622a1 1 0 0 1 3.002 3.002L7.368 18.635a2 2 0 0 1-.855.506l-2.872.838a.5.5 0 0 1-.62-.62l.838-2.872a2 2 0 0 1 .506-.854z" />
                </svg>
                {t("team.roleInstructions", "角色专属指令")}
              </label>
              <Textarea
                disabled={disabled || !expanded}
                aria-label={`${t("team.roleInstructions")} ${roleName}`}
                value={member.role_instructions}
                onChange={(e) => onInstructionsChange(e.target.value)}
                placeholder={t("team.roleInstructionsPlaceholder")}
                rows={3}
                className="team-member-card__textarea"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
