import { useState, useEffect, useCallback, useMemo } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { Plus, Search, Settings2, Sparkles, UsersRound, X } from "lucide-react";
import { nameToGradient } from "../panels/MarketplacePanel/constants";
import { teamApi } from "../../services/api/team";
import type { Team } from "../../types/team";
import { TeamAvatar } from "./TeamAvatar";
import { getTeamFallbackAvatar, getTeamFallbackTag } from "./teamAvatarUtils";
import { useBodyScrollLock } from "../../hooks/useBodyScrollLock";

interface TeamPickerModalProps {
  isOpen: boolean;
  selectedTeamId: string | null;
  onSelect: (teamId: string | null) => void;
  onClose: () => void;
  onCreateNew?: () => void;
  onManageTeams?: () => void;
}

export function TeamPickerModal({
  isOpen,
  selectedTeamId,
  onSelect,
  onClose,
  onCreateNew,
  onManageTeams,
}: TeamPickerModalProps) {
  const { t } = useTranslation();
  const [teams, setTeams] = useState<Team[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  useBodyScrollLock(isOpen);

  useEffect(() => {
    if (!isOpen) return;
    setLoading(true);
    teamApi
      .list(0, 50)
      .then((res) => setTeams(res.teams))
      .catch((err) => console.error("Failed to load teams:", err))
      .finally(() => setLoading(false));
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  const filteredTeams = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return teams;
    return teams.filter(
      (team) =>
        team.name.toLowerCase().includes(q) ||
        team.description?.toLowerCase().includes(q) ||
        (team.tags ?? []).some((tag) => tag.toLowerCase().includes(q)) ||
        team.members.some(
          (member) =>
            member.role_name.toLowerCase().includes(q) ||
            member.role_tags.some((tag) => tag.toLowerCase().includes(q)),
        ),
    );
  }, [query, teams]);

  const handleSelect = useCallback(
    (teamId: string) => {
      onSelect(teamId);
      onClose();
    },
    [onSelect, onClose],
  );

  const handleClear = useCallback(() => {
    onSelect(null);
    onClose();
  }, [onSelect, onClose]);

  const handleCreateNew = useCallback(() => {
    if (!onCreateNew) return;
    onCreateNew();
    onClose();
  }, [onCreateNew, onClose]);

  if (!isOpen) return null;

  return createPortal(
    <div
      data-yields-sidebar
      className="safe-area-viewport-padding fixed inset-0 z-[250] flex items-end justify-center bg-black/30 p-0 sm:items-center sm:p-6"
      onClick={onClose}
    >
      <div
        className="flex max-h-[90dvh] w-full flex-col overflow-hidden rounded-t-2xl shadow-2xl sm:max-w-3xl md:max-w-4xl lg:max-w-5xl xl:max-w-6xl sm:rounded-2xl"
        style={{ background: "var(--theme-bg-card)" }}
        onClick={(event) => event.stopPropagation()}
      >
        <div
          className="flex items-center justify-between border-b px-5 py-4"
          style={{ borderColor: "var(--theme-border)" }}
        >
          <div className="flex items-center gap-3">
            <div className="flex size-10 items-center justify-center rounded-xl bg-stone-100 dark:bg-stone-800">
              <UsersRound size={18} style={{ color: "var(--theme-primary)" }} />
            </div>
            <div>
              <h2
                className="text-base font-semibold"
                style={{ color: "var(--theme-text)" }}
              >
                {t("team.plaza", "团队广场")}
              </h2>
              <p
                className="text-xs"
                style={{ color: "var(--theme-text-secondary)" }}
              >
                {t("team.selectTeamDesc", "选择一个团队进行协作")}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <button
              type="button"
              className="rounded-lg p-2 hover:bg-stone-100 dark:hover:bg-stone-800"
              onClick={onClose}
            >
              <X size={18} />
            </button>
          </div>
        </div>

        <div className="space-y-3 border-b px-5 py-3 border-stone-200/70 dark:border-stone-700/70">
          <div className="flex items-center gap-2">
            {onCreateNew && (
            <button
              type="button"
              onClick={handleCreateNew}
              className="rounded-lg px-3 py-1.5 text-xs font-medium transition-colors"
              style={{
                background: "var(--theme-primary)",
                color: "var(--theme-bg)",
              }}
            >
              <span className="inline-flex items-center gap-1.5">
                <Plus size={13} />
                {t("common.new", "新建")}
              </span>
            </button>
            )}
            {selectedTeamId && (
              <button
                type="button"
                onClick={handleClear}
                className="rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors hover:border-[var(--theme-text-secondary)]"
                style={{
                  borderColor: "var(--theme-border)",
                  color: "var(--theme-text-secondary)",
                }}
              >
                {t("team.clearCurrent", "清除当前团队")}
              </button>
            )}
            {onManageTeams && (
              <button
                type="button"
                onClick={() => {
                  onClose();
                  onManageTeams();
                }}
                className="ml-auto rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors hover:border-[var(--theme-text-secondary)]"
                style={{
                  borderColor: "var(--theme-border)",
                  color: "var(--theme-text-secondary)",
                }}
              >
                <span className="inline-flex items-center gap-1.5">
                  <Settings2 size={13} />
                  {t("team.manage", "管理")}
                </span>
              </button>
            )}
          </div>
          <div className="relative">
            <Search
              size={15}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400"
            />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t("team.search", "搜索团队")}
              className="w-full rounded-lg border bg-transparent py-2 pl-9 pr-3 text-sm outline-none"
              style={{
                borderColor: "var(--theme-border)",
                color: "var(--theme-text)",
              }}
            />
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {loading ? (
            <div className="py-10 text-center text-sm text-stone-500">
              {t("common.loading", "加载中...")}
            </div>
          ) : filteredTeams.length === 0 ? (
            <div className="py-10 text-center text-sm text-stone-500">
              {t("team.noTeams", "暂无团队。创建一个团队以开始协作。")}
            </div>
          ) : (
            <div className="grid auto-grid-cols gap-3">
              {filteredTeams.map((team, index) => {
                const selected = selectedTeamId === team.id;
                const gradient = nameToGradient(team.name);
                const activeCount = team.members.filter(
                  (m) => m.enabled,
                ).length;
                return (
                  <div
                    key={team.id}
                    className="pps-card group flex h-full flex-col overflow-hidden rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg-card)] shadow-sm dark:shadow-none"
                    style={{ animationDelay: `${index * 50}ms` }}
                  >
                    <div
                      className="pps-card__banner relative h-12 shrink-0"
                      style={{
                        background: `linear-gradient(45deg, ${gradient[0]}, ${gradient[1]}, ${gradient[2]})`,
                      }}
                    >
                      {selected && (
                        <span className="scb__status-pill scb__status-pill--installed absolute top-1.5 right-2">
                          {t("personaPresets.using", "使用中")}
                        </span>
                      )}
                    </div>
                    <div className="flex flex-1 flex-col p-4 pt-5">
                      <div className="flex items-start gap-3">
                        <TeamAvatar
                          avatar={team.avatar}
                          fallbackAvatar={getTeamFallbackAvatar(team)}
                          fallbackTag={getTeamFallbackTag(team)}
                          label={team.name}
                          className="team-picker-avatar"
                          iconSize={20}
                        />
                        <div className="min-w-0 flex-1">
                          <h3 className="truncate text-base font-semibold text-[var(--theme-text)] leading-tight">
                            {team.name}
                          </h3>
                          <div className="mt-1.5 flex items-center gap-2 text-[11px] text-[var(--theme-text-secondary)]">
                            <span>
                              {t("team.memberCount", "{{count}} 人", {
                                count: activeCount,
                              })}
                            </span>
                          </div>
                        </div>
                      </div>

                      <p className="mt-3 text-[13px] leading-relaxed text-[var(--theme-text-secondary)] line-clamp-2 min-h-[3.25em]">
                        {team.description ||
                          t("team.defaultDescription", "协同工作的角色团队")}
                      </p>

                      {team.members.length > 0 && (
                        <div className="mt-3 flex flex-wrap gap-1.5">
                          {team.members.slice(0, 3).map((member) => (
                            <span
                              key={member.member_id}
                              className="scb__mini-tag"
                              style={{ cursor: "default" }}
                            >
                              {member.role_name}
                            </span>
                          ))}
                          {team.members.length > 3 && (
                            <span
                              className="scb__mini-tag"
                              style={{ cursor: "default", opacity: 0.7 }}
                            >
                              +{team.members.length - 3}
                            </span>
                          )}
                        </div>
                      )}

                      {(team.tags ?? []).length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {(team.tags ?? []).slice(0, 3).map((tag) => (
                            <span
                              key={tag}
                              className="scb__mini-tag"
                              style={{ cursor: "default", opacity: 0.82 }}
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      )}

                      <div className="flex-1" />

                      <div className="mt-4 flex items-center justify-between gap-2 border-t border-[var(--theme-border)] pt-3">
                        <button
                          type="button"
                          onClick={() => handleSelect(team.id)}
                          className={`pps-card__action ${
                            selected
                              ? "pps-card__action--active"
                              : "pps-card__action--primary"
                          }`}
                        >
                          <Sparkles size={13} />
                          {selected
                            ? t("personaPresets.using", "使用中")
                            : t("personaPresets.use", "使用")}
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
