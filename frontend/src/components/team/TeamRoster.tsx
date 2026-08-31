import { Users } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { TeamMember } from "../../types/team";
import { TeamMemberCard } from "./TeamMemberCard";
import { EmptyState } from "../common/EmptyState";

interface TeamRosterProps {
  members: TeamMember[];
  defaultMemberId: string | null;
  onRemoveMember: (memberId: string) => void;
  onSetDefault: (memberId: string) => void;
  onToggleEnabled: (memberId: string) => void;
  onInstructionsChange: (memberId: string, text: string) => void;
}

export function TeamRoster({
  members,
  defaultMemberId,
  onRemoveMember,
  onSetDefault,
  onToggleEnabled,
  onInstructionsChange,
}: TeamRosterProps) {
  const { t } = useTranslation();
  if (members.length === 0) {
    return (
      <div className="flex h-full min-h-0 flex-col">
        <div className="team-pane-header">
          <div>
            <p className="team-pane-eyebrow">{t("team.rosterView")}</p>
            <h2 className="team-pane-title font-serif">
              {t("team.rosterTitle")}
              <span className="team-pane-count">0</span>
            </h2>
          </div>
        </div>
        <EmptyState
          className="flex-1"
          icon={<Users size={28} />}
          title={t("team.noRolesSelected")}
          description={t("team.noRolesDesc")}
        />
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="team-pane-header">
        <div>
          <p className="team-pane-eyebrow">{t("team.rosterView")}</p>
          <h2 className="team-pane-title font-serif">
            {t("team.rosterTitle")}
            <span className="team-pane-count">{members.length}</span>
          </h2>
        </div>
      </div>
      <div className="team-roster-list">
        {members.map((member) => (
          <TeamMemberCard
            key={member.member_id}
            member={member}
            isDefault={member.member_id === defaultMemberId}
            onRemove={() => onRemoveMember(member.member_id)}
            onSetDefault={() => onSetDefault(member.member_id)}
            onToggleEnabled={() => onToggleEnabled(member.member_id)}
            onInstructionsChange={(text) =>
              onInstructionsChange(member.member_id, text)
            }
          />
        ))}
      </div>
    </div>
  );
}
