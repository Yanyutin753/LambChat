import { useTranslation } from "react-i18next";
import { AgentAvatar } from "../common/AgentAvatar";
import type { GroupMember } from "./AssistantGroupContext";
export function AssistantMentionPopup({
  members,
  highlightedIndex,
  onSelect,
  onHover,
}: {
  members: GroupMember[];
  highlightedIndex: number;
  onSelect: (member: GroupMember) => void;
  onHover: (index: number) => void;
}) {
  const { t } = useTranslation();
  return (
    <div
      className="absolute bottom-full left-0 z-50 mb-2 max-h-64 w-full overflow-y-auto rounded-lg border border-theme-border bg-theme-bg-card p-1 shadow-lg"
      role="listbox"
      aria-label={t("assistants.groupMembers")}
    >
      {members.length ? (
        members.map((member, index) => (
          <button
            type="button"
            role="option"
            key={member.id}
            aria-selected={index === highlightedIndex}
            onMouseDown={(event) => event.preventDefault()}
            onMouseEnter={() => onHover(index)}
            onClick={() => onSelect(member)}
            className={`flex min-h-11 w-full items-center gap-2 rounded px-3 text-left ${
              index === highlightedIndex ? "bg-theme-bg-hover" : ""
            }`}
          >
            <AgentAvatar avatar={member.avatar} seed={member.name} size={24} />
            <span className="truncate">{member.name}</span>
          </button>
        ))
      ) : (
        <p className="p-3 text-13 text-theme-text-secondary">
          {t("common.noResults")}
        </p>
      )}
    </div>
  );
}
