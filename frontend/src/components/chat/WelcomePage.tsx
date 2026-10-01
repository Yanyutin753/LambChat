import {
  memo,
  useMemo,
  useState,
  useCallback,
  useRef,
  useEffect,
  useLayoutEffect,
} from "react";
import { RefreshCw, Sparkles, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { ChatInput } from "./ChatInput";
import { Button } from "../common/ui/Button";
import type { ChatInputProps } from "./ChatInput";
import type { ActiveGoalSpec } from "../../hooks/useAgent/types";
import { ContactAdminDialog } from "../common/ContactAdminDialog";
import { NotificationBanner } from "../notification/NotificationBanner";
import {
  getSelectedPersonaStarterPrompts,
  getSelectedTeamStarterPrompts,
  getWelcomePersonaCards,
  getWelcomePersonaCardClass,
  getWelcomePersonaSkeletonClass,
  getWelcomePersonaSkeletonCount,
  getWelcomeTeamCards,
  getWelcomeSuggestionsContainerClass,
  getWelcomeSuggestionButtonClass,
} from "./welcomeLayout";
import { PersonaAvatarWithLoading } from "../persona/PersonaAvatarWithLoading";
import { useSettingsContext } from "../../contexts/SettingsContext";
import { teamApi } from "../../services/api/team";
import type { PersonaPreset, PersonaPresetSnapshot } from "../../types";
import type { Team } from "../../types/team";
import { TeamAvatar } from "../team/TeamAvatar";
import {
  getTeamFallbackAvatar,
  getTeamFallbackTag,
} from "../team/teamAvatarUtils";
import { WelcomeSkeleton } from "../skeletons/ChatSkeletons";
import {
  beginTeamRequest,
  isWelcomeContentReady,
  shouldRenderWelcomeSkeleton,
  settleTeamRequestFailure,
  settleTeamRequestSuccess,
  type TeamRequestState,
} from "./welcomeReadyState";

interface WelcomePageProps {
  greeting: string;
  subtitle: string;
  refreshLabel: string;
  personasLabel?: string;
  starterPromptsLabel?: string;
  changePersonaLabel?: string;
  personaPresets: PersonaPreset[];
  /** 首次列表请求是否已落地；后台刷新不回退骨架屏（issue #158） */
  personaPresetsLoaded?: boolean;
  hasMorePersonaPresets?: boolean;
  isLoadingMorePersonaPresets?: boolean;
  onLoadMorePersonaPresets?: () => void;
  selectedPersonaPresetId?: string | null;
  selectedPersonaSnapshot?: PersonaPresetSnapshot | null;
  personaPresetsLoading?: boolean;
  personaPresetsError?: string | null;
  onRetryPersonaPresets?: () => void;
  personaPresetsMutating?: boolean;
  currentAgent?: string;
  selectedTeamId?: string | null;
  canSendMessage: boolean;
  chatInputProps: ChatInputProps;
  activeGoal?: ActiveGoalSpec | null;
  onClearActiveGoal?: () => void;
  onUsePersonaPreset?: (
    preset: PersonaPreset,
  ) => Promise<PersonaPresetSnapshot | null>;
  onClearPersonaPreset?: () => void;
  onSelectTeam?: (teamId: string | null) => void;
}

function WelcomeIcon({ className }: { className: string }) {
  return (
    <picture>
      <source
        media="(prefers-reduced-motion: reduce)"
        srcSet="/images/illustrations/lamb-welcome.png"
      />
      <img
        src="/images/lamb.webp"
        alt=""
        aria-hidden="true"
        width={112}
        height={112}
        draggable={false}
        className={`object-contain ${className}`}
      />
    </picture>
  );
}

export const WelcomePage = memo(function WelcomePage({
  greeting,
  subtitle,
  refreshLabel,
  personasLabel,
  starterPromptsLabel,
  changePersonaLabel,
  personaPresets,
  personaPresetsLoaded = false,
  hasMorePersonaPresets,
  isLoadingMorePersonaPresets,
  onLoadMorePersonaPresets,
  selectedPersonaPresetId,
  selectedPersonaSnapshot,
  personaPresetsLoading = false,
  personaPresetsError,
  onRetryPersonaPresets,
  personaPresetsMutating = false,
  currentAgent,
  selectedTeamId,
  canSendMessage,
  chatInputProps,
  activeGoal,
  onClearActiveGoal,
  onUsePersonaPreset,
  onClearPersonaPreset,
  onSelectTeam,
}: WelcomePageProps) {
  const { i18n, t } = useTranslation();
  const navigate = useNavigate();
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [animKey, setAnimKey] = useState(0);
  const [contactAdminOpen, setContactAdminOpen] = useState(false);
  const [mentionQuery, setMentionQuery] = useState<string | null>(null);
  const [pendingInput, setPendingInput] = useState<string | null>(null);
  const [composerFocusRequest, setComposerFocusRequest] = useState(0);
  const [teamRequestState, setTeamRequestState] = useState<
    TeamRequestState<Team>
  >({ requestId: 0, cards: [], isLoading: false, isSettled: false });
  const teamRequestIdRef = useRef(0);
  const [teamRetryKey, setTeamRetryKey] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const galleryRef = useRef<HTMLDivElement>(null);
  const galleryFilterHeightRef = useRef<number | null>(null);

  const handleGalleryScroll = useCallback(() => {
    const el = galleryRef.current;
    if (!el || !hasMorePersonaPresets || !onLoadMorePersonaPresets) return;
    const nearBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 40;
    if (nearBottom) onLoadMorePersonaPresets();
  }, [hasMorePersonaPresets, onLoadMorePersonaPresets]);

  const promptSources = useMemo(() => {
    if (
      selectedPersonaSnapshot &&
      !personaPresets.some(
        (persona) => persona.id === selectedPersonaSnapshot.preset_id,
      )
    ) {
      return [
        ...personaPresets,
        {
          id: selectedPersonaSnapshot.preset_id,
          name: selectedPersonaSnapshot.name,
          starter_prompts: selectedPersonaSnapshot.starter_prompts ?? [],
        },
      ];
    }
    return personaPresets;
  }, [personaPresets, selectedPersonaSnapshot]);

  const roleCards = useMemo(
    () => getWelcomePersonaCards(personaPresets, selectedPersonaPresetId),
    [personaPresets, selectedPersonaPresetId],
  );

  const teamCards = teamRequestState.cards;
  const teamCardsLoading = teamRequestState.isLoading;
  const teamCardsLoaded = teamRequestState.isSettled;

  const welcomeTeamCards = useMemo(
    () => getWelcomeTeamCards(teamCards, selectedTeamId),
    [teamCards, selectedTeamId],
  );

  useLayoutEffect(() => {
    if (currentAgent !== "team") return;
    const requestId = teamRequestIdRef.current + 1;
    teamRequestIdRef.current = requestId;
    setTeamRequestState((state) => beginTeamRequest(state, requestId));
  }, [currentAgent, teamRetryKey]);

  useEffect(() => {
    if (currentAgent !== "team") return;
    const requestId = teamRequestIdRef.current;
    teamApi
      .list(0, 50)
      .then((res) => {
        setTeamRequestState((state) =>
          settleTeamRequestSuccess(state, requestId, res.teams),
        );
      })
      .catch((err) => {
        console.error("Failed to load teams:", err);
        setTeamRequestState((state) =>
          settleTeamRequestFailure(state, requestId),
        );
      });
  }, [currentAgent, teamRetryKey]);

  const filteredCards = useMemo(() => {
    if (!mentionQuery) return roleCards;
    const q = mentionQuery.toLowerCase();
    return roleCards.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        p.description?.toLowerCase().includes(q) ||
        p.tags?.some((tag) => tag.toLowerCase().includes(q)),
    );
  }, [roleCards, mentionQuery]);

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

  const handleMentionQueryChange = useCallback((query: string | null) => {
    if (query === null) galleryFilterHeightRef.current = null;
    else
      galleryFilterHeightRef.current ??=
        galleryRef.current?.getBoundingClientRect().height ?? null;
    setMentionQuery(query);
  }, []);

  const { settings, isLoading: settingsLoading } = useSettingsContext();

  const defaultSuggestions = useMemo(() => {
    const rawValue = settings?.settings?.frontend?.find(
      (s) => s.key === "WELCOME_SUGGESTIONS",
    )?.value;
    const currentLang = i18n.language?.split("-")[0] || "en";
    if (Array.isArray(rawValue)) return rawValue;
    if (rawValue && typeof rawValue === "object") {
      const langMap = rawValue as Record<
        string,
        Array<{ icon: string; text: string }>
      >;
      return langMap[currentLang] || langMap["en"];
    }
    return [];
  }, [settings, i18n.language]);

  const personaStarterPrompts = useMemo(
    () =>
      getSelectedPersonaStarterPrompts(
        promptSources,
        selectedPersonaPresetId,
        i18n.language,
        selectedPersonaPresetId ? defaultSuggestions : [],
      ),
    [promptSources, selectedPersonaPresetId, i18n.language, defaultSuggestions],
  );

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

  const handleSuggestionClick = (text: string) => {
    if (!canSendMessage) {
      setContactAdminOpen(true);
      return;
    }
    setPendingInput(text);
  };

  const handleChangePersona = useCallback(() => {
    if (!onClearPersonaPreset) return;
    setIsRefreshing(true);
    onClearPersonaPreset();
    handleMentionQueryChange(null);
    setAnimKey((k) => k + 1);
    setTimeout(() => setIsRefreshing(false), 400);
  }, [onClearPersonaPreset, handleMentionQueryChange]);

  const handleChangeTeam = useCallback(() => {
    if (!onSelectTeam) return;
    setIsRefreshing(true);
    onSelectTeam?.(null);
    setComposerFocusRequest((request) => request + 1);
    handleMentionQueryChange(null);
    setAnimKey((k) => k + 1);
    setTimeout(() => setIsRefreshing(false), 400);
  }, [onSelectTeam, handleMentionQueryChange]);

  const handlePersonaClick = useCallback(
    async (preset: PersonaPreset) => {
      if (personaPresetsMutating) return;
      await onUsePersonaPreset?.(preset);
    },
    [onUsePersonaPreset, personaPresetsMutating],
  );

  const handleTeamClick = useCallback(
    (team: Team) => {
      if (!onSelectTeam) return;
      onSelectTeam?.(team.id);
      setComposerFocusRequest((request) => request + 1);
    },
    [onSelectTeam],
  );

  const isAgentReady = !!currentAgent;
  const shouldProjectMentionsToWelcome =
    isAgentReady &&
    (currentAgent === "team" ? !selectedTeamId : !selectedPersonaPresetId);

  useEffect(() => {
    if (!shouldProjectMentionsToWelcome) {
      handleMentionQueryChange(null);
    }
  }, [shouldProjectMentionsToWelcome, handleMentionQueryChange]);

  const showTeamCards = currentAgent === "team" && !selectedTeamId;
  const showPersonaCards =
    isAgentReady && currentAgent !== "team" && !selectedPersonaPresetId;
  const showStarterPrompts =
    isAgentReady &&
    currentAgent !== "team" &&
    !!selectedPersonaPresetId &&
    personaStarterPrompts.length > 0;
  const showTeamStarterPrompts =
    currentAgent === "team" &&
    !!selectedTeamId &&
    teamStarterPrompts.length > 0;
  const canChangePersona =
    isAgentReady &&
    currentAgent !== "team" &&
    !!selectedPersonaPresetId &&
    !!onClearPersonaPreset;
  const canChangeTeam =
    currentAgent === "team" && !!selectedTeamId && !!onSelectTeam;
  const showSelectionActions = canChangePersona || canChangeTeam;
  const activeStarterPrompts =
    currentAgent === "team"
      ? teamStarterPrompts.length > 0
        ? teamStarterPrompts
        : defaultSuggestions
      : personaStarterPrompts.length > 0
        ? personaStarterPrompts
        : defaultSuggestions;
  const displayCards = mentionQuery ? filteredCards : roleCards;
  const displayTeamCards = mentionQuery ? filteredTeamCards : welcomeTeamCards;
  const shouldShowTeamSkeletons =
    showTeamCards && (teamCardsLoading || !teamCardsLoaded);
  const personaSkeletonCount = getWelcomePersonaSkeletonCount(
    personaPresetsLoading,
    displayCards.length,
  );
  const teamSkeletonCount = getWelcomePersonaSkeletonCount(
    shouldShowTeamSkeletons,
    displayTeamCards.length,
  );
  const galleryError = showTeamCards
    ? teamRequestState.hasError
      ? t("common.loadFailed")
      : null
    : showPersonaCards
      ? personaPresetsError
      : null;
  const retryGallery = () => {
    rootRef.current?.querySelector<HTMLElement>('[role="textbox"]')?.focus();
    if (showTeamCards) setTeamRetryKey((key) => key + 1);
    else onRetryPersonaPresets?.();
  };
  // Whether data has loaded but is empty
  const isTeamEmpty =
    showTeamCards &&
    !galleryError &&
    !teamCardsLoading &&
    teamCardsLoaded &&
    welcomeTeamCards.length === 0;
  const isPersonaEmpty =
    showPersonaCards &&
    !galleryError &&
    !personaPresetsLoading &&
    personaPresetsLoaded &&
    roleCards.length === 0;
  // Whether to show the choice-card gallery section (persona or team).
  const showGallerySection = showPersonaCards || showTeamCards;
  const galleryEmpty =
    !galleryError &&
    ((showPersonaCards &&
      personaPresetsLoaded &&
      personaSkeletonCount === 0 &&
      displayCards.length === 0) ||
      (showTeamCards &&
        teamSkeletonCount === 0 &&
        displayTeamCards.length === 0));
  const welcomeContentReady = isWelcomeContentReady({
    settingsLoading,
    currentAgent,
    personaPresetsLoading,
    personaPresetsLoaded,
    teamRequestSettled: teamCardsLoaded,
  });
  // 骨架只覆盖首次加载：一旦内容就绪过，后续 refetch 不再卸载整个页面
  // （WelcomePage 里挂着 ChatInput 和打开中的弹窗状态，issue #158）。
  const hasEverBeenReadyRef = useRef(false);
  if (welcomeContentReady) {
    hasEverBeenReadyRef.current = true;
  }

  if (
    shouldRenderWelcomeSkeleton(
      welcomeContentReady,
      hasEverBeenReadyRef.current,
    )
  ) {
    return <WelcomeSkeleton />;
  }

  return (
    <div
      ref={rootRef}
      className="welcome-root relative flex h-full flex-col items-center justify-center px-4"
    >
      {/* Greeting section */}
      <div className="welcome-hero relative flex flex-col items-center mb-1 sm:mb-2 md:mb-2.5 xl:mb-3 2xl:mb-3 w-full sm:max-w-[44rem] md:max-w-[46rem] lg:max-w-[48rem] xl:max-w-[50rem] 2xl:max-w-[52rem]">
        {/* App icon (mobile only) */}
        <div className="sm:hidden relative mb-2">
          <WelcomeIcon className="welcome-icon relative size-12" />
        </div>

        {/* Greeting */}
        <h1
          className="welcome-greeting max-w-full text-[1.5rem] sm:text-[1.875rem] md:text-[2rem] lg:text-[2.25rem] xl:text-[2.35rem] 2xl:text-[2.5rem] font-semibold tracking-[-0.02em] leading-[1.2] text-center font-serif"
          style={{ color: "var(--theme-text)" }}
        >
          <WelcomeIcon className="welcome-icon hidden sm:inline-block size-12 xl:size-14 2xl:size-16 mr-4 align-text-bottom" />
          {greeting}
        </h1>
        {/* Subtle subtitle prompt */}
        <p
          className="welcome-subtitle mt-1.5 sm:mt-2 md:mt-2.5 xl:mt-3 2xl:mt-3 text-14 sm:text-16 md:text-17 xl:text-18 2xl:text-18 text-center font-serif"
          style={{ color: "var(--theme-text-secondary)" }}
        >
          {subtitle}
        </p>
      </div>

      {/* ChatInput centered — the focal point */}
      <div className="welcome-input flex w-full flex-col mx-auto sm:max-w-[44rem] md:max-w-[46rem] lg:max-w-[48rem] xl:max-w-[50rem] 2xl:max-w-[52rem]">
        <ChatInput
          {...chatInputProps}
          focusRequest={
            (chatInputProps.focusRequest ?? 0) + composerFocusRequest
          }
          onMentionQueryChange={
            shouldProjectMentionsToWelcome
              ? handleMentionQueryChange
              : undefined
          }
          pendingInput={pendingInput}
          onPendingInputConsumed={() => setPendingInput(null)}
          className="mx-auto w-full px-2"
          activeGoal={activeGoal || null}
          onClearActiveGoal={onClearActiveGoal}
          goalLabel={t("chat.goal.active", "目标")}
          goalDurationLabel={t("chat.goal.running", "运行")}
          goalClearLabel={t("chat.goal.clear", "清除目标")}
          showHelpMenu
        />
      </div>

      {(showGallerySection ||
        showStarterPrompts ||
        showTeamStarterPrompts ||
        showSelectionActions) && (
        <div
          className={getWelcomeSuggestionsContainerClass(
            showGallerySection ? "personas" : "prompts",
          )}
        >
          <div className="welcome-suggestions-header flex items-center justify-between mb-2 sm:mb-2.5 md:mb-2.5 xl:mb-3 2xl:mb-3">
            <div
              className="flex items-center gap-1.5 text-12 sm:text-13 md:text-13 font-medium font-serif"
              style={{ color: "var(--theme-text-secondary)" }}
            >
              <Sparkles
                size={11}
                className="opacity-60 sm:w-3.5 sm:h-3.5 xl:w-4 xl:h-4 2xl:w-4 2xl:h-4"
              />
              <span>
                {showTeamCards || (canChangeTeam && !showTeamStarterPrompts)
                  ? t("team.plaza", "团队广场")
                  : showStarterPrompts || showTeamStarterPrompts
                    ? starterPromptsLabel ||
                      t("personaPresets.starterPrompts", "开始对话")
                    : personasLabel || t("personaPresets.title", "角色")}
              </span>
            </div>
            <div className="flex items-center gap-2">
              {showGallerySection && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => navigate(showTeamCards ? "/team" : "/persona")}
                  rightIcon={<ChevronRight size={12} />}
                >
                  {t("common.manage")}
                </Button>
              )}
              {showSelectionActions && (
                <button
                  onClick={
                    canChangeTeam ? handleChangeTeam : handleChangePersona
                  }
                  className="welcome-refresh-btn flex items-center gap-1.5 px-2 py-1 rounded-lg text-11 sm:text-12 md:text-12 font-medium transition-all duration-300 cursor-pointer font-serif"
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
                  <span>
                    {canChangeTeam
                      ? t("team.change", "更换团队")
                      : changePersonaLabel ||
                        refreshLabel ||
                        t("personaPresets.change", "更换角色")}
                  </span>
                </button>
              )}
            </div>
          </div>
          {galleryError && (
            <div
              role="alert"
              className="flex flex-col items-center gap-3 py-3 text-center text-14 text-theme-text-secondary"
            >
              <p className="max-w-full break-words">{galleryError}</p>
              {(showTeamCards || onRetryPersonaPresets) && (
                <Button size="lg" onClick={retryGallery}>
                  {t("common.retry")}
                </Button>
              )}
            </div>
          )}
          <div
            key={animKey}
            ref={showGallerySection ? galleryRef : undefined}
            onScroll={showPersonaCards ? handleGalleryScroll : undefined}
            style={
              mentionQuery !== null && galleryFilterHeightRef.current !== null
                ? {
                    minHeight: `min(40dvh, ${galleryFilterHeightRef.current}px)`,
                  }
                : undefined
            }
            className={
              showGallerySection
                ? [
                    "welcome-persona-gallery relative pb-1 sm:pb-0",
                    galleryEmpty && "welcome-persona-gallery--empty",
                    (teamSkeletonCount > 0 || personaSkeletonCount > 0) &&
                      "welcome-persona-gallery--loading",
                  ]
                    .filter(Boolean)
                    .join(" ")
                : "welcome-suggestions-grid-wrapper"
            }
          >
            {galleryEmpty && (
              <div
                role="status"
                className="flex min-h-11 flex-col items-center justify-center gap-1 py-3 text-center text-14 text-theme-text-secondary"
              >
                <p>
                  {showTeamCards
                    ? isTeamEmpty
                      ? t("team.empty")
                      : t("team.noMatchingTeams")
                    : isPersonaEmpty
                      ? t("persona.empty")
                      : t("personaPresets.noMatch")}
                </p>
                {!isTeamEmpty && !isPersonaEmpty && (
                  <p className="text-12">
                    {t("personaPresets.tryOtherFilters")}
                  </p>
                )}
              </div>
            )}
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
                const activeCount = team.members.filter(
                  (m) => m.enabled,
                ).length;
                return (
                  <button
                    key={team.id}
                    onClick={() => handleTeamClick(team)}
                    disabled={!onSelectTeam}
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
                        <div className="flex items-center justify-between gap-2">
                          <span className="welcome-persona-name-row relative flex items-center gap-1.5 min-w-0">
                            <span
                              className="welcome-persona-name truncate text-13 sm:text-14 font-bold leading-[1.3] transition-colors duration-300 group-hover:text-[var(--theme-text)] font-serif"
                              style={{ color: "var(--theme-text)" }}
                            >
                              {team.name}
                            </span>
                          </span>
                          <span
                            className="welcome-persona-tag shrink-0 inline-flex rounded-full px-1.5 py-[1px] text-10 leading-none font-medium"
                            style={{
                              backgroundColor: "var(--theme-primary-light)",
                              color: "var(--theme-primary)",
                            }}
                          >
                            {t("team.memberCount", "{{count}} 人", {
                              count: activeCount,
                            })}
                          </span>
                        </div>
                        <span
                          className="welcome-persona-description block mt-1 text-12 leading-[1.5]"
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
            {showPersonaCards &&
              Array.from({ length: personaSkeletonCount }).map((_, i) => (
                <div
                  key={`persona-skeleton-${i}`}
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
            {showPersonaCards &&
              displayCards.map((preset, i) => {
                return (
                  <button
                    key={preset.id}
                    onClick={() => handlePersonaClick(preset)}
                    disabled={personaPresetsMutating}
                    className={getWelcomePersonaCardClass(i)}
                    style={{
                      backgroundColor: "var(--theme-bg-card)",
                      borderColor: "var(--theme-border)",
                      animationDelay: `${i * 60}ms`,
                    }}
                  >
                    <span className="welcome-card-shimmer" aria-hidden="true" />
                    <span className="welcome-persona-header relative flex items-center gap-3">
                      <PersonaAvatarWithLoading
                        preset={preset}
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
                            className="welcome-persona-name truncate text-13 sm:text-14 font-bold leading-[1.3] transition-colors duration-300 group-hover:text-[var(--theme-text)] font-serif"
                            style={{ color: "var(--theme-text)" }}
                          >
                            {preset.name}
                          </span>
                        </span>
                        {preset.description && (
                          <span
                            className="welcome-persona-description block mt-1 text-12 leading-[1.5]"
                            style={{
                              color:
                                "var(--theme-text-tertiary, var(--theme-text-secondary))",
                            }}
                          >
                            {preset.description}
                          </span>
                        )}
                      </span>
                    </span>
                  </button>
                );
              })}
            {showPersonaCards && isLoadingMorePersonaPresets && (
              <div className="welcome-persona-loading sticky bottom-0 left-0 right-0 flex items-center justify-center py-1 pointer-events-none z-10">
                <span className="welcome-persona-loading-dot" />
                <span className="welcome-persona-loading-dot" />
                <span className="welcome-persona-loading-dot" />
              </div>
            )}
            {(showStarterPrompts || showTeamStarterPrompts) && (
              <div className="welcome-suggestions-grid grid grid-cols-1 sm:grid-cols-2 gap-2 sm:gap-2.5 md:gap-2.5 xl:gap-3 2xl:gap-3">
                {activeStarterPrompts.map((suggestion, i) => (
                  <button
                    key={suggestion.text}
                    onClick={() => handleSuggestionClick(suggestion.text)}
                    className={getWelcomeSuggestionButtonClass(i)}
                    style={{
                      backgroundColor: "var(--theme-bg-card)",
                      borderColor: "var(--theme-border)",
                      animationDelay: `${i * 60}ms`,
                    }}
                  >
                    {/* Hover shimmer layer */}
                    <span className="welcome-card-shimmer" aria-hidden="true" />
                    <span
                      className="relative flex items-center justify-center size-6 sm:size-7 xl:size-8 2xl:size-8 rounded-lg text-13 sm:text-15 xl:text-18 2xl:text-18 shrink-0 transition-transform duration-300 group-hover:scale-110"
                      style={{
                        backgroundColor: "var(--theme-primary-light)",
                        color: "var(--theme-primary)",
                      }}
                    >
                      {suggestion.icon || "✨"}
                    </span>
                    <span
                      className="relative text-12.5 sm:text-13.5 leading-[1.4] sm:leading-[1.45] truncate transition-colors duration-300 group-hover:text-[var(--theme-text)]"
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
      )}

      <NotificationBanner />

      <ContactAdminDialog
        isOpen={contactAdminOpen}
        onClose={() => setContactAdminOpen(false)}
        reason="noPermission"
      />
    </div>
  );
});
