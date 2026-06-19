/**
 * Team selector for channel configuration.
 * Used when a channel is bound to the team agent.
 */
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, ChevronDown, UsersRound } from "lucide-react";
import { useTranslation } from "react-i18next";
import { teamApi } from "../../../services/api/team";
import type { Team } from "../../../types/team";
import { TeamAvatar } from "../../team/TeamAvatar";
import {
  getTeamFallbackAvatar,
  getTeamFallbackTag,
} from "../../team/teamAvatarUtils";

interface ChannelTeamSelectProps {
  value: string | null | undefined;
  onChange: (teamId: string | null) => void;
  disabled?: boolean;
  loadTeams?: boolean;
}

export function ChannelTeamSelect({
  value,
  onChange,
  disabled = false,
  loadTeams = true,
}: ChannelTeamSelectProps) {
  const { t } = useTranslation();
  const [teams, setTeams] = useState<Team[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [dropdownStyle, setDropdownStyle] = useState<React.CSSProperties>({});
  const ref = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    if (!loadTeams) {
      setTeams([]);
      setLoading(false);
      return () => {
        cancelled = true;
      };
    }
    setLoading(true);
    teamApi
      .list(0, 50)
      .then((res) => {
        if (!cancelled) setTeams(res.teams || []);
      })
      .catch(() => {
        if (!cancelled) setTeams([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [loadTeams]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        ref.current &&
        !ref.current.contains(target) &&
        dropdownRef.current &&
        !dropdownRef.current.contains(target)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  useLayoutEffect(() => {
    if (!open || !ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const w = Math.max(rect.width, 220);
    const left = Math.max(16, Math.min(rect.left, vw - w - 16));
    const spaceBelow = vh - rect.bottom - 16;
    const spaceAbove = rect.top - 16;
    const preferBelow = spaceBelow >= 220 || spaceBelow >= spaceAbove;

    setDropdownStyle({
      position: "fixed",
      top: preferBelow ? rect.bottom + 4 : undefined,
      bottom: preferBelow ? undefined : vh - rect.top + 4,
      left,
      width: w,
      zIndex: 9999,
    });
  }, [open]);

  const selectedTeam = useMemo(
    () => teams.find((team) => team.id === value) || null,
    [teams, value],
  );

  const displayText = selectedTeam
    ? selectedTeam.name
    : value
      ? value
      : loading
      ? t("common.loading", "Loading...")
      : t("channel.defaultTeam", "不指定团队");

  return (
    <div className="es-field">
      <label className="es-label">
        <div className="flex items-center gap-1.5">
          <UsersRound size={14} />
          {t("channel.team", "团队")}
        </div>
      </label>
      <div ref={ref} className="relative">
        <button
          type="button"
          disabled={loading || disabled}
          onClick={() => !loading && !disabled && setOpen((v) => !v)}
          className="glass-input es-select-btn"
        >
          {selectedTeam && (
            <TeamAvatar
              avatar={selectedTeam.avatar}
              fallbackAvatar={getTeamFallbackAvatar(selectedTeam)}
              fallbackTag={getTeamFallbackTag(selectedTeam)}
              label={selectedTeam.name}
              className="team-toolbar-avatar"
              iconSize={14}
            />
          )}
          <span className="truncate">{displayText}</span>
          <ChevronDown
            size={15}
            className="shrink-0 text-[var(--theme-text-secondary)] transition-transform duration-200"
            style={{ transform: open ? "rotate(180deg)" : undefined }}
          />
        </button>
      </div>

      {open &&
        createPortal(
          <div
            ref={dropdownRef}
            className="glass-select-dropdown channel-persona-select__dropdown"
            style={dropdownStyle}
          >
            <button
              type="button"
              onClick={() => {
                onChange(null);
                setOpen(false);
              }}
              className={`glass-select-option ${!value ? "active" : ""}`}
            >
              {!value && (
                <Check size={14} className="glass-select-option-check" />
              )}
              <span className="glass-select-option-label">
                {t("channel.defaultTeam", "不指定团队")}
              </span>
            </button>

            {teams.map((team) => {
              const active = team.id === value;
              return (
                <button
                  key={team.id}
                  type="button"
                  onClick={() => {
                    onChange(team.id);
                    setOpen(false);
                  }}
                  className={`glass-select-option ${active ? "active" : ""}`}
                >
                  {active && (
                    <Check size={14} className="glass-select-option-check" />
                  )}
                  <span className="flex min-w-0 items-center gap-2">
                    <TeamAvatar
                      avatar={team.avatar}
                      fallbackAvatar={getTeamFallbackAvatar(team)}
                      fallbackTag={getTeamFallbackTag(team)}
                      label={team.name}
                      className="team-toolbar-avatar"
                      iconSize={14}
                    />
                    <span className="truncate">{team.name}</span>
                  </span>
                </button>
              );
            })}
          </div>,
          document.body,
        )}

      <p className="es-hint">
        {t(
          "channel.teamHint",
          "Select which team handles messages from this channel",
        )}
      </p>
    </div>
  );
}
