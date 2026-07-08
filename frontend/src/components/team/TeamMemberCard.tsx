import { useState } from "react";
import { ChevronDown, Cpu, Star, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { TeamMember } from "../../types/team";
import type { ModelOption } from "../../services/api/model";
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
  isDefault: boolean;
  onRemove: () => void;
  onSetDefault: () => void;
  onToggleEnabled: () => void;
  onInstructionsChange: (text: string) => void;
  availableModels?: ModelOption[];
  onModelChange?: (modelId: string | null) => void;
}

export function TeamMemberCard({
  member,
  isDefault,
  onRemove,
  onSetDefault,
  onToggleEnabled,
  onInstructionsChange,
  availableModels = [],
  onModelChange,
}: TeamMemberCardProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(!!member.role_instructions);

  const selectedModel = member.model_id
    ? availableModels.find((model) => model.id === member.model_id)
    : null;
  const modelLabel = member.model_id
    ? selectedModel?.label || selectedModel?.value || member.model_id
    : t("team.followSessionModel", "跟随会话模型");
  const modelOptions: SelectOption[] = [
    { value: "", label: t("team.followSessionModel", "跟随会话模型") },
    ...availableModels.map((model) => ({
      value: model.id,
      label: model.label || model.value,
    })),
  ];

  return (
    <div
      className={`list-item-card ${
        expanded ? "list-item-card--expanded" : ""
      } ${member.enabled ? "" : "list-item-card--disabled"}`}
    >
      <div className="list-item-card__body">
        {/* Main row: avatar + name + tags + actions */}
        <div className="list-item-card__top">
          <div className="team-member-card__avatar-btn">
            {isPersonaImageAvatar(member.role_avatar) ||
            isEmojiAvatar(member.role_avatar) ? (
              <div className="team-member-card__avatar">
                <PersonaAvatarImage
                  avatar={
                    isEmojiAvatar(member.role_avatar)
                      ? getEmojiAvatarUrl(member.role_avatar)
                      : member.role_avatar
                  }
                  alt=""
                  className="team-member-card__avatar-img"
                />
              </div>
            ) : (
              <div className="team-member-card__avatar team-member-card__avatar--icon">
                <PersonaAvatarIcon
                  avatar={member.role_avatar}
                  primaryTag={member.role_tags[0]}
                  size={18}
                  className="text-[var(--theme-primary)]"
                />
              </div>
            )}
          </div>

          <div className="list-item-card__identity">
            <div className="team-member-card__identity-header">
              <span className="list-item-card__name">
                {member.role_name || t("team.unnamedRole")}
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
            </div>
            <span className="team-member-card__meta-row">
              <span className="team-member-card__model" title={modelLabel}>
                <Cpu size={11} />
                <span>{modelLabel}</span>
              </span>
            </span>
          </div>

          {/* Inline actions */}
          <div className="list-item-card__actions">
            <Tooltip
              content={isDefault ? t("team.defaultRole") : t("team.setDefault")}
            >
              <IconButton
                onClick={onSetDefault}
                icon={
                  <Star size={14} fill={isDefault ? "currentColor" : "none"} />
                }
                variant={isDefault ? "primary" : "ghost"}
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
                onClick={onRemove}
                icon={<Trash2 size={14} />}
                variant="ghost"
                size="sm"
                className="team-member-card__action-btn team-member-card__action-btn--danger"
              />
            </Tooltip>
          </div>

          {/* Toggle */}
          <button
            onClick={onToggleEnabled}
            className={`team-toggle ${member.enabled ? "team-toggle--on" : ""}`}
            title={
              member.enabled ? t("team.disableRole") : t("team.enableRole")
            }
            type="button"
            role="switch"
            aria-checked={member.enabled}
          />

          {/* Expand chevron */}
          <button
            onClick={() => setExpanded(!expanded)}
            className="team-member-card__expand-btn"
            type="button"
          >
            <ChevronDown
              size={13}
              className={`team-member-card__expand-icon ${
                expanded ? "team-member-card__expand-icon--open" : ""
              }`}
            />
          </button>
        </div>

        {/* Collapsible instructions with smooth animation */}
        <div
          className={`team-member-card__collapse ${
            expanded ? "team-member-card__collapse--open" : ""
          }`}
        >
          <div className="list-item-card__instructions">
            <div className="team-member-card__instructions-divider" />
            <div className="team-member-card__field">
              <label className="ppe-label">
                <Cpu size={13} className="ppe-label-icon" />
                {t("team.memberModel", "成员模型")}
              </label>
              <Select
                value={member.model_id ?? ""}
                onChange={(v) => onModelChange?.(v || null)}
                options={modelOptions}
                disabled={!onModelChange}
                placeholder={t("team.followSessionModel", "跟随会话模型")}
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
