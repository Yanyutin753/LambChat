import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { ChevronRight, Plus, RefreshCw, Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import type { CoreWelcomeSurfaceContribution } from "../../extensions/coreContributions";
import { teamApi } from "../../services/api/team";
import type { Team } from "../../types/team";
import { TeamAvatar } from "../team/TeamAvatar";
import {
  getTeamFallbackAvatar,
  getTeamFallbackTag,
} from "../team/teamAvatarUtils";
import {
  getSelectedTeamStarterPrompts,
  getWelcomePersonaCardClass,
  getWelcomePersonaSkeletonClass,
  getWelcomePersonaSkeletonCount,
  getWelcomeSuggestionsContainerClass,
  getWelcomeSuggestionButtonClass,
  getWelcomeTeamCards,
  type WelcomeStarterPrompt,
} from "./welcomeLayout";

export interface WelcomeSurfaceRendererProps {
  contribution: CoreWelcomeSurfaceContribution;
  mentionQuery: string | null;
  defaultSuggestions: WelcomeStarterPrompt[];
  selectedTeamId?: string | null;
  starterPromptsLabel?: string;
  refreshLabel?: string;
  onPluginOptionChange?: (pluginId: string, key: string, value: unknown) => void;
  onUseSuggestion: (text: string) => void;
}

type WelcomeSurfaceRendererComponent = (
  props: WelcomeSurfaceRendererProps,
) => ReactNode;

function AgentTeamWelcomeSurface({
  contribution,
  mentionQuery,
  defaultSuggestions,
  selectedTeamId,
  starterPromptsLabel,
  refreshLabel,
  onPluginOptionChange,
  onUseSuggestion,
}: WelcomeSurfaceRendererProps) {
  const { i18n, t } = useTranslation();
  const navigate = useNavigate();
  const [teamCards, setTeamCards] = useState<Team[]>([]);
  const [teamCardsLoading, setTeamCardsLoading] = useState(false);
  const [teamCardsLoaded, setTeamCardsLoaded] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [animKey, setAnimKey] = useState(0);
  const optionBinding = contribution.optionBinding;

  useEffect(() => {
    let cancelled = false;
    setTeamCardsLoaded(false);
    setTeamCardsLoading(true);
    teamApi
      .list(0, 50)
      .then((res) => {
        if (!cancelled) setTeamCards(res.teams);
      })
      .catch((err) => console.error("Failed to load teams:", err))
      .finally(() => {
        if (!cancelled) {
          setTeamCardsLoaded(true);
          setTeamCardsLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const welcomeTeamCards = useMemo(
    () => getWelcomeTeamCards(teamCards, selectedTeamId),
    [teamCards, selectedTeamId],
  );

  const filteredTeamCards = useMemo(() => {
    if (!mentionQuery) return welcomeTeamCards;
    const q = mentionQuery.toLowerCase();
    return welcomeTeamCards.filter(
      (team) =>
        team.name.toLowerCase().includes(q) ||
        team.description?.toLowerCase().includes(q) ||
        team.members.some(
          (member) =>
            member.role_name.toLowerCase().includes(q) ||
            member.role_tags.some((tag) => tag.toLowerCase().includes(q)),
        ),
    );
  }, [welcomeTeamCards, mentionQuery]);

  const teamStarterPrompts = useMemo(
    () =>
      getSelectedTeamStarterPrompts(
        teamCards,
        selectedTeamId,
        i18n.language,
        selectedTeamId ? defaultSuggestions : [],
      ),
    [teamCards, selectedTeamId, i18n.language, defaultSuggestions],
  );

  const handleChangeTeam = useCallback(() => {
    if (!onPluginOptionChange || !optionBinding) return;
    setIsRefreshing(true);
    onPluginOptionChange(optionBinding.pluginId, optionBinding.key, null);
    setAnimKey((key) => key + 1);
    setTimeout(() => setIsRefreshing(false), 400);
  }, [onPluginOptionChange, optionBinding]);

  const handleTeamClick = useCallback(
    (team: Team) => {
      if (!optionBinding) return;
      onPluginOptionChange?.(optionBinding.pluginId, optionBinding.key, team.id);
    },
    [onPluginOptionChange, optionBinding],
  );

  const showTeamCards = !selectedTeamId;
  const showTeamStarterPrompts =
    !!selectedTeamId && teamStarterPrompts.length > 0;
  const canChangeTeam = !!selectedTeamId && !!onPluginOptionChange && !!optionBinding;
  const canSelectTeam = Boolean(onPluginOptionChange && optionBinding);
  const displayTeamCards = mentionQuery ? filteredTeamCards : welcomeTeamCards;
  const shouldShowTeamSkeletons =
    showTeamCards && (teamCardsLoading || !teamCardsLoaded);
  const teamSkeletonCount = getWelcomePersonaSkeletonCount(
    shouldShowTeamSkeletons,
    displayTeamCards.length,
  );
  const isTeamEmpty =
    showTeamCards && !teamCardsLoading && displayTeamCards.length === 0;
  const activeStarterPrompts =
    teamStarterPrompts.length > 0 ? teamStarterPrompts : defaultSuggestions;
  const showChoiceCards = showTeamCards && !isTeamEmpty;

  if (!showTeamCards && !showTeamStarterPrompts && !canChangeTeam) return null;

  return (
    <div
      className={getWelcomeSuggestionsContainerClass(
        showChoiceCards ? "personas" : "prompts",
      )}
    >
      <div className="welcome-suggestions-header flex items-center justify-between mb-2 sm:mb-2.5 md:mb-2.5 xl:mb-3 2xl:mb-3">
        <div
          className="flex items-center gap-1.5 text-xs sm:text-[13px] md:text-[13px] font-medium font-serif"
          style={{ color: "var(--theme-text-secondary)" }}
        >
          <Sparkles
            size={11}
            className="opacity-60 sm:w-3.5 sm:h-3.5 xl:w-4 xl:h-4 2xl:w-4 2xl:h-4"
          />
          <span>
            {showTeamCards
              ? isTeamEmpty
                ? t("team.empty", "暂无团队")
                : t("team.plaza", "团队广场")
              : starterPromptsLabel ||
                t("personaPresets.starterPrompts", "开始对话")}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {showTeamCards && isTeamEmpty && (
            <button
              onClick={() => navigate("/agent-team")}
              className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] sm:text-[12px] md:text-[12px] font-medium transition-all duration-300 cursor-pointer font-serif"
              style={{
                color: "var(--theme-primary)",
                backgroundColor: "var(--theme-primary-light)",
              }}
            >
              <Plus size={12} />
              <span>{t("team.addNew", "新建团队")}</span>
            </button>
          )}
          {showTeamCards && !isTeamEmpty && (
            <button
              onClick={() => navigate("/agent-team")}
              className="flex items-center gap-0.5 px-2 py-1 rounded-lg text-[11px] sm:text-[12px] md:text-[12px] font-medium transition-all duration-300 cursor-pointer font-serif"
              style={{
                color: "var(--theme-text-secondary)",
                backgroundColor: "transparent",
              }}
            >
              <span>{t("common.manage", "管理")}</span>
              <ChevronRight size={12} />
            </button>
          )}
          {canChangeTeam && (
            <button
              onClick={handleChangeTeam}
              className="welcome-refresh-btn flex items-center gap-1.5 px-2 py-1 rounded-lg text-[11px] sm:text-[12px] md:text-[12px] font-medium transition-all duration-300 cursor-pointer font-serif"
              style={{
                color: "var(--theme-text-secondary)",
                backgroundColor: "transparent",
              }}
            >
              <RefreshCw
                size={12}
                className={
                  isRefreshing
                    ? "animate-spin"
                    : "xl:w-3.5 xl:h-3.5 2xl:w-3.5 2xl:h-3.5"
                }
              />
              <span>{t("team.change", refreshLabel || "更换团队")}</span>
            </button>
          )}
        </div>
      </div>
      <div
        key={animKey}
        className={
          showTeamCards
            ? [
                "welcome-persona-gallery relative pb-1 sm:pb-0",
                teamSkeletonCount > 0 && "welcome-persona-gallery--loading",
              ]
                .filter(Boolean)
                .join(" ")
            : "welcome-suggestions-grid-wrapper"
        }
      >
        {showTeamCards &&
          Array.from({ length: teamSkeletonCount }).map((_, i) => (
            <div
              key={`team-skeleton-${i}`}
              className={getWelcomePersonaSkeletonClass()}
              style={{
                backgroundColor: "var(--theme-bg-card)",
                borderColor: "var(--theme-border)",
              }}
              aria-hidden="true"
            >
              <span className="welcome-skeleton-avatar" />
              <span className="welcome-skeleton-info">
                <span className="welcome-skeleton-name-row">
                  <span className="welcome-skeleton-line welcome-skeleton-title" />
                  <span className="welcome-skeleton-line welcome-skeleton-tag" />
                </span>
                <span className="welcome-skeleton-line welcome-skeleton-desc" />
              </span>
            </div>
          ))}
        {showTeamCards &&
          displayTeamCards.map((team, i) => {
            const activeCount = team.members.filter((member) => member.enabled).length;
            return (
              <button
                key={team.id}
                onClick={() => handleTeamClick(team)}
                disabled={!canSelectTeam}
                className={getWelcomePersonaCardClass(i)}
                style={{
                  backgroundColor: "var(--theme-bg-card)",
                  borderColor: "var(--theme-border)",
                  animationDelay: `${i * 60}ms`,
                }}
              >
                <span className="welcome-card-shimmer" aria-hidden="true" />
                <span className="welcome-persona-header relative flex items-center gap-3">
                  <TeamAvatar
                    avatar={team.avatar}
                    fallbackAvatar={getTeamFallbackAvatar(team)}
                    fallbackTag={getTeamFallbackTag(team)}
                    label={team.name}
                    className="welcome-persona-avatar relative flex items-center justify-center size-11 rounded-xl shrink-0 overflow-hidden transition-transform duration-300 group-hover:scale-105"
                    imgClassName="h-full w-full object-cover"
                    iconSize={22}
                    style={{
                      background:
                        "linear-gradient(135deg, var(--theme-primary-light) 0%, color-mix(in srgb, var(--theme-primary) 10%, var(--theme-bg-card)) 100%)",
                      color: "var(--theme-primary)",
                    }}
                  />
                  <span className="welcome-persona-info min-w-0 flex-1">
                    <span className="welcome-persona-name-row relative flex items-center gap-1.5">
                      <span
                        className="welcome-persona-name truncate text-[13px] sm:text-[14px] font-bold leading-[1.3] transition-colors duration-300 group-hover:text-[var(--theme-text)] font-serif"
                        style={{ color: "var(--theme-text)" }}
                      >
                        {team.name}
                      </span>
                      <span
                        className="welcome-persona-tag shrink-0 inline-flex rounded-full px-1.5 py-[1px] text-[10px] leading-none font-medium"
                        style={{
                          backgroundColor: "var(--theme-primary-light)",
                          color: "var(--theme-primary)",
                        }}
                      >
                        {t("team.memberCount", "{{count}} 人", {
                          count: activeCount,
                        })}
                      </span>
                    </span>
                    <span
                      className="welcome-persona-description block mt-1 text-[12px] leading-[1.5]"
                      style={{
                        color:
                          "var(--theme-text-tertiary, var(--theme-text-secondary))",
                      }}
                    >
                      {team.description ||
                        t("team.defaultDescription", "协同工作的角色团队")}
                    </span>
                  </span>
                </span>
              </button>
            );
          })}
        {showTeamStarterPrompts && (
          <div className="welcome-suggestions-grid grid grid-cols-1 sm:grid-cols-2 gap-2 sm:gap-2.5 md:gap-2.5 xl:gap-3 2xl:gap-3">
            {activeStarterPrompts.map((suggestion, i) => (
              <button
                key={suggestion.text}
                onClick={() => onUseSuggestion(suggestion.text)}
                className={getWelcomeSuggestionButtonClass(i)}
                style={{
                  backgroundColor: "var(--theme-bg-card)",
                  borderColor: "var(--theme-border)",
                  animationDelay: `${i * 60}ms`,
                }}
              >
                <span className="welcome-card-shimmer" aria-hidden="true" />
                <span
                  className="relative flex items-center justify-center size-6 sm:size-7 xl:size-8 2xl:size-8 rounded-lg text-[13px] sm:text-[15px] xl:text-lg 2xl:text-lg shrink-0 transition-transform duration-300 group-hover:scale-110"
                  style={{
                    backgroundColor: "var(--theme-primary-light)",
                    color: "var(--theme-primary)",
                  }}
                >
                  {suggestion.icon || "✓"}
                </span>
                <span
                  className="relative text-[12.5px] sm:text-[13.5px] leading-[1.4] sm:leading-[1.45] truncate transition-colors duration-300 group-hover:text-[var(--theme-text)]"
                  style={{ color: "var(--theme-text-secondary)" }}
                >
                  {suggestion.text}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export const WELCOME_SURFACE_RENDERERS: Readonly<
  Record<string, WelcomeSurfaceRendererComponent>
> = {
  "agent_team.TeamWelcomeSurface": AgentTeamWelcomeSurface,
};

export function WelcomeSurfaceRenderer(props: WelcomeSurfaceRendererProps) {
  const Renderer = WELCOME_SURFACE_RENDERERS[props.contribution.renderer];
  return Renderer ? <Renderer {...props} /> : null;
}
