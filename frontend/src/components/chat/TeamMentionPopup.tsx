import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Check } from "lucide-react";
import type { Team } from "../../types/team";
import { TeamAvatar } from "../team/TeamAvatar";
import {
  getTeamFallbackAvatar,
  getTeamFallbackTag,
} from "../team/teamAvatarUtils";

interface TeamMentionPopupProps {
  teams: Team[];
  highlightedIndex: number;
  selectedTeamId?: string | null;
  isLoading?: boolean;
  onSelect: (team: Team) => void;
  onHover: (index: number) => void;
  onClose: () => void;
  placement?: {
    left: number;
    width: number;
    bottom: number;
    maxHeight: number;
  } | null;
}

function SkeletonItems() {
  return (
    <>
      {[1, 2, 3, 4, 5].map((n) => (
        <div key={n} className="mention-skeleton-item">
          <div className="mention-skeleton-avatar" />
          <div className="mention-skeleton-text">
            <div className="mention-skeleton-name" />
            <div className="mention-skeleton-desc" />
          </div>
        </div>
      ))}
    </>
  );
}

export function TeamMentionPopup({
  teams,
  highlightedIndex,
  selectedTeamId,
  isLoading,
  onSelect,
  onHover,
  onClose,
  placement,
}: TeamMentionPopupProps) {
  const { t } = useTranslation();
  const anchorRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);

  useEffect(() => {
    const el = itemRefs.current[highlightedIndex];
    if (el) el.scrollIntoView({ block: "nearest" });
  }, [highlightedIndex]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (anchorRef.current && !anchorRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [onClose]);

  return (
    <div
      ref={anchorRef}
      className="mention-popup-anchor"
      style={
        placement
          ? ({
              "--mention-popup-left": `${placement.left}px`,
              "--mention-popup-width": `${placement.width}px`,
              "--mention-popup-bottom": `${placement.bottom}px`,
              "--mention-popup-max-height": `${placement.maxHeight}px`,
            } as React.CSSProperties)
          : undefined
      }
    >
      <div className="mention-popup">
        <div className="mention-popup-content">
          {isLoading && teams.length === 0 ? (
            <div className="mention-popup-list">
              <SkeletonItems />
            </div>
          ) : teams.length === 0 ? (
            <div className="mention-popup-empty">
              {t("team.noMatchingTeams", "没有匹配的团队")}
            </div>
          ) : (
            <div className="mention-popup-list">
              {teams.map((team, index) => {
                const isActive = index === highlightedIndex;
                const isSelected = selectedTeamId === team.id;
                return (
                  <button
                    key={team.id}
                    ref={(el) => {
                      itemRefs.current[index] = el;
                    }}
                    type="button"
                    role="option"
                    aria-selected={isActive}
                    className={`mention-popup-item ${
                      isActive ? "mention-popup-item--active" : ""
                    }`}
                    onClick={() => onSelect(team)}
                    onMouseEnter={() => onHover(index)}
                  >
                    <TeamAvatar
                      avatar={team.avatar}
                      fallbackAvatar={getTeamFallbackAvatar(team)}
                      fallbackTag={getTeamFallbackTag(team)}
                      label={team.name}
                      className="mention-popup-avatar"
                      imgClassName="mention-popup-avatar-img"
                      iconSize={14}
                    />
                    <div className="mention-popup-text">
                      <span className="mention-popup-name font-serif">
                        {team.name}
                        {isSelected && (
                          <Check
                            size={13}
                            className="inline-block ml-1.5 opacity-60"
                          />
                        )}
                      </span>
                      <span className="mention-popup-desc">
                        {team.description ||
                          `${team.members.filter((m) => m.enabled).length} ${t(
                            "team.members",
                            "成员",
                          )}`}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
