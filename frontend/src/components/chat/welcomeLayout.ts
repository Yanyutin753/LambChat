import type { LocalizedText, PersonaStarterPrompt } from "../../types";

interface WelcomePersonaLike {
  id: string;
  name: string;
  is_favorite?: boolean;
  is_pinned?: boolean;
  last_used_at?: string | null;
  usage_count?: number;
  updated_at?: string;
  created_at?: string;
  starter_prompts?: PersonaStarterPrompt[];
}

interface WelcomeTeamLike {
  id: string;
  name: string;
  is_favorite?: boolean;
  is_pinned?: boolean;
  last_used_at?: string | null;
  updated_at?: string;
  created_at?: string;
  starter_prompts?: PersonaStarterPrompt[];
}

export interface WelcomeStarterPrompt {
  icon: string | null;
  text: string;
}

export function getWelcomePersonaCardClass(_index: number): string {
  return [
    "welcome-card",
    "welcome-persona-card",
    "group",
    "relative",
    "flex",
    "min-w-[15.75rem]",
    "snap-start",
    "flex-col",
    "py-3",
    "px-3",
    "rounded-2xl",
    "border",
    "text-left",
    "cursor-pointer",
    "transition-all",
    "duration-300",
    "overflow-hidden",
    "sm:min-w-0",
  ]
    .filter(Boolean)
    .join(" ");
}

export function getWelcomePersonaSkeletonClass(): string {
  return getWelcomePersonaCardClass(0) + " welcome-persona-skeleton";
}

export function getWelcomePersonaSkeletonCount(
  isLoading = false,
  visibleCount = 0,
  skeletonCount = 12,
): number {
  return isLoading && visibleCount === 0 ? skeletonCount : 0;
}

export function getWelcomeSuggestionButtonClass(_index: number): string {
  return "welcome-card welcome-suggestion-pill group relative flex items-center gap-2 sm:gap-3 md:gap-3 xl:gap-3.5 2xl:gap-3.5 rounded-xl border px-3 py-2 sm:px-4 sm:py-3 text-left cursor-pointer transition-all duration-300 overflow-hidden";
}

export const WELCOME_SUGGESTIONS_CLASS_NAME =
  "welcome-suggestions relative mx-auto px-2 sm:px-0 sm:mt-2 md:mt-2.5 xl:mt-3 2xl:mt-3 w-full sm:max-w-[48rem] md:max-w-[50rem] lg:max-w-[52rem] xl:max-w-[54rem] 2xl:max-w-[56rem]";

export const WELCOME_PERSONA_CLASS_NAME =
  "welcome-suggestions relative mx-auto px-4 sm:px-10 sm:mt-2 md:mt-2.5 xl:mt-3 2xl:mt-3 w-full sm:max-w-[44rem] md:max-w-[46rem] lg:max-w-[48rem] xl:max-w-[50rem] 2xl:max-w-[52rem]";

export function getWelcomeSuggestionsContainerClass(
  variant: "personas" | "prompts",
): string {
  return variant === "personas"
    ? WELCOME_PERSONA_CLASS_NAME
    : WELCOME_SUGGESTIONS_CLASS_NAME;
}

export function resolveLocalizedText(
  value: LocalizedText,
  language = "en",
): string {
  if (typeof value === "string") return value;

  const normalizedLanguage = language.toLowerCase();
  const baseLanguage = normalizedLanguage.split("-")[0];
  return (
    value[language] ||
    value[normalizedLanguage] ||
    value[baseLanguage] ||
    value.en ||
    value.zh ||
    Object.values(value)[0] ||
    ""
  );
}

export function getWelcomePersonaCards<T extends WelcomePersonaLike>(
  personas: T[],
  selectedPersonaId: string | null | undefined,
  limit?: number,
): T[] {
  if (selectedPersonaId) return [];
  const cards = [...personas].sort(compareWelcomePersonas);
  return typeof limit === "number" ? cards.slice(0, limit) : cards;
}

export function getWelcomeTeamCards<T extends WelcomeTeamLike>(
  teams: T[],
  selectedTeamId: string | null | undefined,
  limit?: number,
): T[] {
  if (selectedTeamId) return [];
  const cards = [...teams].sort(compareWelcomePersonas);
  return typeof limit === "number" ? cards.slice(0, limit) : cards;
}

function timeValue(value: string | null | undefined): number {
  if (!value) return 0;
  const time = Date.parse(value);
  return Number.isFinite(time) ? time : 0;
}

export function compareWelcomePersonas<
  T extends WelcomePersonaLike | WelcomeTeamLike,
>(a: T, b: T): number {
  const aUsage = "usage_count" in a ? a.usage_count : 0;
  const bUsage = "usage_count" in b ? b.usage_count : 0;
  return (
    Number(Boolean(b.is_pinned)) - Number(Boolean(a.is_pinned)) ||
    Number(Boolean(b.is_favorite)) - Number(Boolean(a.is_favorite)) ||
    timeValue(b.updated_at) - timeValue(a.updated_at) ||
    timeValue(b.created_at) - timeValue(a.created_at) ||
    timeValue(b.last_used_at) - timeValue(a.last_used_at) ||
    Number(bUsage || 0) - Number(aUsage || 0)
  );
}

export function getSelectedPersonaStarterPrompts(
  personas: WelcomePersonaLike[],
  selectedPersonaId: string | null | undefined,
  language = "en",
  fallbackPrompts: WelcomeStarterPrompt[] = [],
): WelcomeStarterPrompt[] {
  return getSelectedStarterPrompts(
    personas,
    selectedPersonaId,
    language,
    fallbackPrompts,
  );
}

export function getSelectedTeamStarterPrompts(
  teams: WelcomeTeamLike[],
  selectedTeamId: string | null | undefined,
  language = "en",
  fallbackPrompts: WelcomeStarterPrompt[] = [],
): WelcomeStarterPrompt[] {
  return getSelectedStarterPrompts(
    teams,
    selectedTeamId,
    language,
    fallbackPrompts,
  );
}

function getSelectedStarterPrompts<T extends WelcomeTeamLike>(
  items: T[],
  selectedItemId: string | null | undefined,
  language: string,
  fallbackPrompts: WelcomeStarterPrompt[],
): WelcomeStarterPrompt[] {
  const selected = items.find((item) => item.id === selectedItemId);
  if (!selected) return fallbackPrompts;

  const prompts = (selected.starter_prompts ?? [])
    .map((prompt) => ({
      icon: prompt.icon?.trim() || null,
      text: resolveLocalizedText(prompt.text, language).trim(),
    }))
    .filter((prompt) => prompt.text.length > 0);

  return prompts.length > 0 ? prompts : fallbackPrompts;
}
