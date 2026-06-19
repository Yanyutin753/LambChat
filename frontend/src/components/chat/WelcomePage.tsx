import { memo, useMemo, useState, useCallback, useRef, useEffect } from "react";
import { RefreshCw, Sparkles, UserRound, ChevronRight, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { ChatInput } from "./ChatInput";
import type { ChatInputProps } from "./ChatInput";
import type { ActiveGoalSpec } from "../../hooks/useAgent/types";
import { ContactAdminDialog } from "../common/ContactAdminDialog";
import { NotificationBanner } from "../notification/NotificationBanner";
import { ImageWithSkeleton } from "./ChatMessage/ImageWithSkeleton";
import {
  getSelectedPersonaStarterPrompts,
  getWelcomePersonaCards,
  getWelcomePersonaCardClass,
  getWelcomePersonaSkeletonClass,
  getWelcomePersonaSkeletonCount,
  getWelcomeSuggestionsContainerClass,
  getWelcomeSuggestionButtonClass,
} from "./welcomeLayout";
import { PersonaAvatarWithLoading } from "../persona/PersonaAvatarWithLoading";
import { useSettingsContext } from "../../contexts/SettingsContext";
import type { PersonaPreset, PersonaPresetSnapshot } from "../../types";
import { buildWelcomeSurfaceContributions } from "../../extensions/coreContributions";
import { WelcomeSurfaceRenderer } from "./welcomeSurfaceRenderers";

const WELCOME_ICON_SRC = "/images/lamb.webp";

interface WelcomePageProps {
  greeting: string;
  subtitle: string;
  refreshLabel: string;
  personasLabel?: string;
  starterPromptsLabel?: string;
  changePersonaLabel?: string;
  personaPresets: PersonaPreset[];
  hasMorePersonaPresets?: boolean;
  isLoadingMorePersonaPresets?: boolean;
  onLoadMorePersonaPresets?: () => void;
  selectedPersonaPresetId?: string | null;
  selectedPersonaSnapshot?: PersonaPresetSnapshot | null;
  personaPresetsLoading?: boolean;
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
}

function WelcomeIcon({
  className,
  label,
}: {
  className: string;
  label?: string;
}) {
  return (
    <ImageWithSkeleton
      src={WELCOME_ICON_SRC}
      alt={label ?? ""}
      skipUrlResolve
      inline
      className={className}
      style={{ objectFit: "contain" }}
    />
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
  hasMorePersonaPresets,
  isLoadingMorePersonaPresets,
  onLoadMorePersonaPresets,
  selectedPersonaPresetId,
  selectedPersonaSnapshot,
  personaPresetsLoading = false,
  personaPresetsMutating = false,
  currentAgent,
  selectedTeamId,
  canSendMessage,
  chatInputProps,
  activeGoal,
  onClearActiveGoal,
  onUsePersonaPreset,
  onClearPersonaPreset,
}: WelcomePageProps) {
  const { i18n, t } = useTranslation();
  const navigate = useNavigate();
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [animKey, setAnimKey] = useState(0);
  const [contactAdminOpen, setContactAdminOpen] = useState(false);
  const [mentionQuery, setMentionQuery] = useState<string | null>(null);
  const [pendingInput, setPendingInput] = useState<string | null>(null);
  const galleryRef = useRef<HTMLDivElement>(null);

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

  const filteredCards = useMemo(() => {
    if (!mentionQuery) return roleCards;
    const q = mentionQuery.toLowerCase();
    return roleCards.filter(
      (preset) =>
        preset.name.toLowerCase().includes(q) ||
        preset.description?.toLowerCase().includes(q) ||
        preset.tags?.some((tag) => tag.toLowerCase().includes(q)),
    );
  }, [roleCards, mentionQuery]);

  const handleMentionQueryChange = useCallback(
    (query: string | null) => setMentionQuery(query),
    [],
  );

  const { settings } = useSettingsContext();

  const defaultSuggestions = useMemo(() => {
    const rawValue = settings?.settings?.frontend?.find(
      (setting) => setting.key === "WELCOME_SUGGESTIONS",
    )?.value;
    const currentLang = i18n.language?.split("-")[0] || "en";
    if (Array.isArray(rawValue)) return rawValue;
    if (rawValue && typeof rawValue === "object") {
      const langMap = rawValue as Record<
        string,
        Array<{ icon: string; text: string }>
      >;
      return langMap[currentLang] || langMap.en || [];
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

  const handleSuggestionClick = useCallback(
    (text: string) => {
      if (!canSendMessage) {
        setContactAdminOpen(true);
        return;
      }
      setPendingInput(text);
    },
    [canSendMessage],
  );

  const handleChangePersona = useCallback(() => {
    if (!onClearPersonaPreset) return;
    setIsRefreshing(true);
    onClearPersonaPreset();
    setMentionQuery(null);
    setAnimKey((key) => key + 1);
    setTimeout(() => setIsRefreshing(false), 400);
  }, [onClearPersonaPreset]);

  const handlePersonaClick = useCallback(
    async (preset: PersonaPreset) => {
      if (personaPresetsMutating) return;
      await onUsePersonaPreset?.(preset);
    },
    [onUsePersonaPreset, personaPresetsMutating],
  );

  const welcomeSurfaceContributions = useMemo(
    () =>
      buildWelcomeSurfaceContributions(chatInputProps.runtimePlugins, {
        agentId: currentAgent ?? null,
      }),
    [chatInputProps.runtimePlugins, currentAgent],
  );
  const activeWelcomeSurface = welcomeSurfaceContributions[0] ?? null;
  const hasWelcomeSurface = Boolean(activeWelcomeSurface);
  const isAgentReady = !!currentAgent;
  const shouldProjectMentionsToWelcome =
    isAgentReady &&
    (hasWelcomeSurface ? !selectedTeamId : !selectedPersonaPresetId);

  useEffect(() => {
    if (!shouldProjectMentionsToWelcome) {
      setMentionQuery(null);
    }
  }, [shouldProjectMentionsToWelcome]);

  const showPersonaCards =
    isAgentReady && !hasWelcomeSurface && !selectedPersonaPresetId;
  const showStarterPrompts =
    isAgentReady &&
    !hasWelcomeSurface &&
    !!selectedPersonaPresetId &&
    personaStarterPrompts.length > 0;
  const canChangePersona =
    isAgentReady &&
    !hasWelcomeSurface &&
    !!selectedPersonaPresetId &&
    !!onClearPersonaPreset;
  const activeStarterPrompts =
    personaStarterPrompts.length > 0 ? personaStarterPrompts : defaultSuggestions;
  const displayCards = mentionQuery ? filteredCards : roleCards;
  const personaSkeletonCount = getWelcomePersonaSkeletonCount(
    personaPresetsLoading,
    displayCards.length,
  );
  const isPersonaEmpty =
    showPersonaCards && !personaPresetsLoading && displayCards.length === 0;
  const showGallerySection = showPersonaCards;
  const showChoiceCards = showPersonaCards && !isPersonaEmpty;

  return (
    <div className="welcome-root relative flex h-full flex-col items-center justify-center px-4">
      <div className="welcome-hero relative flex flex-col items-center mb-1 sm:mb-2 md:mb-2.5 xl:mb-3 2xl:mb-3 w-full sm:max-w-[44rem] md:max-w-[46rem] lg:max-w-[48rem] xl:max-w-[50rem] 2xl:max-w-[52rem]">
        <div className="sm:hidden relative mb-2">
          <WelcomeIcon
            label="LambChat"
            className="welcome-icon relative size-12 object-contain rounded-full"
          />
        </div>
        <h1
          className="welcome-greeting max-w-full text-[1.5rem] sm:text-[1.875rem] md:text-[2rem] lg:text-[2.25rem] xl:text-[2.35rem] 2xl:text-[2.5rem] font-semibold tracking-[-0.02em] leading-[1.2] text-center font-serif"
          style={{ color: "var(--theme-text)" }}
        >
          <WelcomeIcon className="welcome-icon hidden sm:inline-block size-12 xl:size-14 2xl:size-16 mr-4 align-text-bottom object-contain rounded-full" />
          {greeting}
        </h1>
        <p
          className="welcome-subtitle mt-1.5 sm:mt-2 md:mt-2.5 xl:mt-3 2xl:mt-3 text-sm sm:text-base md:text-[17px] xl:text-lg 2xl:text-lg text-center font-serif"
          style={{ color: "var(--theme-text-secondary)" }}
        >
          {subtitle}
        </p>
      </div>

      <div className="welcome-input flex w-full flex-col mx-auto sm:max-w-[44rem] md:max-w-[46rem] lg:max-w-[48rem] xl:max-w-[50rem] 2xl:max-w-[52rem]">
        <ChatInput
          {...chatInputProps}
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
          goalLabel={t("chat.goal.active", "Goal")}
          goalDurationLabel={t("chat.goal.running", "Running")}
          goalClearLabel={t("chat.goal.clear", "Clear goal")}
          showHelpMenu
        />
      </div>

      {activeWelcomeSurface && (
        <WelcomeSurfaceRenderer
          contribution={activeWelcomeSurface}
          mentionQuery={mentionQuery}
          defaultSuggestions={defaultSuggestions}
          selectedTeamId={selectedTeamId}
          starterPromptsLabel={starterPromptsLabel}
          refreshLabel={refreshLabel}
          onPluginOptionChange={chatInputProps.onPluginOptionChange}
          onUseSuggestion={handleSuggestionClick}
        />
      )}

      {(showGallerySection || showStarterPrompts || canChangePersona) && (
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
                {showStarterPrompts
                  ? starterPromptsLabel ||
                    t("personaPresets.starterPrompts", "Start a conversation")
                  : isPersonaEmpty
                    ? t("persona.empty", "No personas")
                    : personasLabel || t("personaPresets.title", "Personas")}
              </span>
            </div>
            <div className="flex items-center gap-2">
              {showPersonaCards && isPersonaEmpty && (
                <button
                  onClick={() => navigate("/persona")}
                  className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] sm:text-[12px] md:text-[12px] font-medium transition-all duration-300 cursor-pointer font-serif"
                  style={{
                    color: "var(--theme-primary)",
                    backgroundColor: "var(--theme-primary-light)",
                  }}
                >
                  <Plus size={12} />
                  <span>{t("persona.addNew", "New persona")}</span>
                </button>
              )}
              {showPersonaCards && !isPersonaEmpty && (
                <button
                  onClick={() => navigate("/persona")}
                  className="flex items-center gap-0.5 px-2 py-1 rounded-lg text-[11px] sm:text-[12px] md:text-[12px] font-medium transition-all duration-300 cursor-pointer font-serif"
                  style={{
                    color: "var(--theme-text-secondary)",
                    backgroundColor: "transparent",
                  }}
                >
                  <span>{t("common.manage", "Manage")}</span>
                  <ChevronRight size={12} />
                </button>
              )}
              {canChangePersona && (
                <button
                  onClick={handleChangePersona}
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
                  <span>
                    {changePersonaLabel ||
                      refreshLabel ||
                      t("personaPresets.change", "Change persona")}
                  </span>
                </button>
              )}
            </div>
          </div>
          <div
            key={animKey}
            ref={showGallerySection ? galleryRef : undefined}
            onScroll={showPersonaCards ? handleGalleryScroll : undefined}
            className={
              showGallerySection
                ? [
                    "welcome-persona-gallery relative pb-1 sm:pb-0",
                    personaSkeletonCount > 0 &&
                      "welcome-persona-gallery--loading",
                  ]
                    .filter(Boolean)
                    .join(" ")
                : "welcome-suggestions-grid-wrapper"
            }
          >
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
                const primaryTag = preset.tags[0] || "";
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
                        fallbackIcon={<UserRound size={22} />}
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
                            {preset.name}
                          </span>
                          {primaryTag && (
                            <span
                              className="welcome-persona-tag shrink-0 inline-flex rounded-full px-1.5 py-[1px] text-[10px] leading-none font-medium"
                              style={{
                                backgroundColor: "var(--theme-primary-light)",
                                color: "var(--theme-primary)",
                              }}
                            >
                              {primaryTag}
                            </span>
                          )}
                        </span>
                        {preset.description && (
                          <span
                            className="welcome-persona-description block mt-1 text-[12px] leading-[1.5]"
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
            <div
              className={
                showStarterPrompts
                  ? "welcome-suggestions-grid grid grid-cols-1 sm:grid-cols-2 gap-2 sm:gap-2.5 md:gap-2.5 xl:gap-3 2xl:gap-3"
                  : undefined
              }
            >
              {showStarterPrompts &&
                activeStarterPrompts.map((suggestion, i) => (
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
                    <span className="welcome-card-shimmer" aria-hidden="true" />
                    <span
                      className="relative flex items-center justify-center size-6 sm:size-7 xl:size-8 2xl:size-8 rounded-lg text-[13px] sm:text-[15px] xl:text-lg 2xl:text-lg shrink-0 transition-transform duration-300 group-hover:scale-110"
                      style={{
                        backgroundColor: "var(--theme-primary-light)",
                        color: "var(--theme-primary)",
                      }}
                    >
                      {suggestion.icon || "+"}
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
