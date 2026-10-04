import { DialogCloseButton } from "../common/DialogCloseButton";
import { ModalSurface } from "../common/ModalSurface";
import { useState, useEffect, useCallback, useRef } from "react";

import { useTranslation } from "react-i18next";
import { Plus, Search, Settings2, Sparkles, UsersRound } from "lucide-react";
import { nameToGradient } from "../panels/MarketplacePanel/constants";
import { teamApi } from "../../services/api/team";
import type { Team } from "../../types/team";
import { TeamAvatar } from "./TeamAvatar";
import { getTeamFallbackAvatar, getTeamFallbackTag } from "./teamAvatarUtils";

import { PanelSearchInput } from "../common/PanelSearchInput";
import { subscribeTeamsChanged } from "../../hooks/teamEvents";
import { Pagination } from "../common/Pagination";
import { ResourceCardTags } from "../common/ResourceCardTags";

const PAGE_SIZE = 20;

interface TeamPickerModalProps {
  isOpen: boolean;
  selectedTeamId: string | null;
  onSelect: (teamId: string | null) => void;
  onClose: () => void;
  onCreateNew: () => void;
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
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const requestRef = useRef(0);
  const loadTeams = useCallback(async () => {
    if (!isOpen) return;
    const request = ++requestRef.current;
    setLoading(true);
    setLoadError(false);
    try {
      const result = await teamApi.list({
        skip: (page - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
        q: query.trim() || undefined,
      });
      if (request !== requestRef.current) return;
      setTeams(result.teams);
      setTotal(result.total);
    } catch {
      if (request === requestRef.current) setLoadError(true);
    } finally {
      if (request === requestRef.current) setLoading(false);
    }
  }, [isOpen, page, query]);

  useEffect(() => {
    if (!isOpen) return;
    void loadTeams();
    const unsubscribe = subscribeTeamsChanged(() => void loadTeams());
    return () => {
      requestRef.current += 1;
      unsubscribe();
    };
  }, [isOpen, loadTeams]);

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
    onClose();
    onCreateNew();
  }, [onCreateNew, onClose]);

  if (!isOpen) return null;

  return (
    <ModalSurface
      className="modal-wide"
      open={isOpen}
      onClose={onClose}
      dismissible={true}
    >
      <div
        className="resource-picker flex max-h-[90dvh] w-full flex-col overflow-hidden rounded-t-2xl shadow-2xl sm:max-w-3xl md:max-w-4xl lg:max-w-5xl xl:max-w-6xl sm:rounded-2xl safe-area-bottom"
        style={{ background: "var(--theme-bg-card)" }}
        onClick={(event) => event.stopPropagation()}
      >
        <div
          className="resource-picker-header flex items-center justify-between border-b px-5 py-4"
          style={{ borderColor: "var(--theme-border)" }}
        >
          <div className="flex items-center gap-3">
            <div className="flex size-10 items-center justify-center rounded-xl bg-theme-bg-subtle">
              <UsersRound size={18} style={{ color: "var(--theme-primary)" }} />
            </div>
            <div>
              <h2
                className="text-16 font-semibold"
                style={{ color: "var(--theme-text)" }}
              >
                {t("team.plaza", "团队广场")}
              </h2>
              <p
                className="text-12"
                style={{ color: "var(--theme-text-secondary)" }}
              >
                {t("team.selectTeamDesc", "选择一个团队进行协作")}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <DialogCloseButton onClick={onClose} />
          </div>
        </div>

        <div className="resource-picker-toolbar space-y-3 border-b px-5 py-3 border-theme-border/70">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleCreateNew}
              className="inline-flex h-8 items-center justify-center rounded-lg px-3 text-12 font-medium transition-colors"
              style={{
                background: "var(--theme-primary)",
                color: "var(--theme-bg)",
              }}
            >
              <span className="inline-flex h-full items-center justify-center gap-1.5">
                <Plus size={13} />
                {t("common.new", "新建")}
              </span>
            </button>
            {selectedTeamId && (
              <button
                type="button"
                onClick={handleClear}
                className="rounded-lg border px-3 py-1.5 text-12 font-medium transition-colors hover:border-[var(--theme-text-secondary)]"
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
                title={t("team.manage")}
                aria-label={t("team.manage")}
                onClick={() => {
                  onClose();
                  onManageTeams();
                }}
                className="ml-auto inline-flex h-8 items-center justify-center rounded-lg border px-3 text-12 font-medium transition-colors hover:border-[var(--theme-text-secondary)]"
                style={{
                  borderColor: "var(--theme-border)",
                  color: "var(--theme-text-secondary)",
                }}
              >
                <span className="inline-flex h-full items-center justify-center gap-1.5">
                  <Settings2 size={13} />
                  <span className="hidden sm:inline">
                    {t("team.manage", "管理")}
                  </span>
                </span>
              </button>
            )}
          </div>
          <div className="relative">
            <Search
              size={15}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-theme-text-tertiary"
            />
            <PanelSearchInput
              value={query}
              onValueChange={(value) => {
                setPage(1);
                setQuery(value);
              }}
              maxLength={100}
              placeholder={t("team.search", "搜索团队")}
              className="w-full rounded-lg border bg-transparent py-2 pl-9 pr-3 text-14 outline-none"
              style={{
                borderColor: "var(--theme-border)",
                color: "var(--theme-text)",
              }}
            />
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {loading ? (
            <div className="py-10 text-center text-14 text-theme-text-secondary">
              {t("common.loading", "加载中...")}
            </div>
          ) : loadError ? (
            <div
              role="alert"
              className="py-10 text-center text-14 text-theme-text-secondary"
            >
              <p>{t("common.loadFailed")}</p>
              <button
                type="button"
                className="btn-secondary mt-3"
                onClick={() => void loadTeams()}
              >
                {t("common.retry")}
              </button>
            </div>
          ) : teams.length === 0 ? (
            <div className="py-10 text-center text-14 text-theme-text-secondary">
              {query.trim()
                ? t("team.noMatchingTeams")
                : t("team.noTeams", "暂无团队。创建一个团队以开始协作。")}
            </div>
          ) : (
            <div className="grid auto-grid-cols gap-3">
              {teams.map((team, index) => {
                const selected = selectedTeamId === team.id;
                const gradient = nameToGradient(team.name);
                const activeCount = team.members.filter(
                  (m) => m.enabled,
                ).length;
                return (
                  <div
                    key={team.id}
                    className="pps-card group flex h-full flex-col overflow-hidden rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg-card)] shadow-sm dark:shadow-none"
                    style={{ animationDelay: `${Math.min(index * 30, 180)}ms` }}
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
                          <h3
                            className="line-clamp-2 text-16 font-semibold font-serif text-theme-text leading-tight"
                            title={team.name}
                          >
                            {team.name}
                          </h3>
                          <div className="mt-1.5 flex items-center gap-2 text-11 text-[var(--theme-text-secondary)]">
                            <span>
                              {t("team.memberCount", "{{count}} 人", {
                                count: activeCount,
                              })}
                            </span>
                          </div>
                        </div>
                      </div>

                      <p className="mt-3 text-13 leading-relaxed text-[var(--theme-text-secondary)] line-clamp-2 min-h-[3.25em]">
                        {team.description ||
                          t("team.defaultDescription", "协同工作的角色团队")}
                      </p>

                      {team.members.length > 0 && (
                        <div className="mt-3 font-serif">
                          <ResourceCardTags
                            tags={[
                              ...new Set(
                                team.members.map((member) => member.role_name),
                              ),
                            ]}
                          />
                        </div>
                      )}
                      {(team.tags ?? []).length > 0 && (
                        <div className="mt-2">
                          <ResourceCardTags tags={team.tags} />
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
        <div
          hidden={loadError}
          className="border-t border-theme-border px-5 py-3 empty:hidden"
        >
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={total}
            onChange={setPage}
          />
        </div>
      </div>
    </ModalSurface>
  );
}
