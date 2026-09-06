import {
  DEFAULT_THINKING_LEVEL_STORAGE_KEY,
  normalizeThinkingOptionValue,
} from "../components/layout/AppContent/useAgentOptions";
import { SEND_MODIFIER_STORAGE_KEY } from "./sendModifier";
import {
  FONT_SCALE_EXTERNAL_CHANGE_EVENT,
  FONT_SCALE_STORAGE_KEY,
  isFontScale,
} from "../utils/fontScale";
import { THEME_SCHEDULE_STORAGE_KEY } from "../utils/themeDom";

export const SIDEBAR_COLLAPSED_STORAGE_KEY = "lamb-sidebar-collapsed";
export const PROJECTS_COLLAPSED_STORAGE_KEY = "lamb-projects-collapsed";
export const CHATS_COLLAPSED_STORAGE_KEY = "lamb-chats-collapsed";
export const SCHEDULED_TASKS_COLLAPSED_STORAGE_KEY =
  "lamb-scheduled-tasks-collapsed";
export const NEWLINE_MODIFIER_STORAGE_KEY = SEND_MODIFIER_STORAGE_KEY;
export const DEFAULT_MODEL_ID_STORAGE_KEY = "defaultModelId";
export const DEFAULT_MODEL_STORAGE_KEY = "defaultModel";

type UserMetadataPreferences = {
  language?: unknown;
  theme?: unknown;
  theme_schedule?: unknown;
  newlineModifier?: unknown;
  defaultThinkingLevel?: unknown;
  sidebarCollapsed?: unknown;
  projectsCollapsed?: unknown;
  chatsCollapsed?: unknown;
  scheduledTasksCollapsed?: unknown;
  defaultModelId?: unknown;
  defaultModel?: unknown;
  fontScale?: unknown;
};

type StorageLike = Pick<Storage, "setItem">;

type ApplyUserMetadataPreferencesOptions = {
  metadata?: UserMetadataPreferences | null;
  localStorage: StorageLike;
  changeLanguage: (language: string) => void;
  dispatchEvent: (event: CustomEvent) => void;
};

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

export function applyUserMetadataPreferences({
  metadata,
  localStorage,
  changeLanguage,
  dispatchEvent,
}: ApplyUserMetadataPreferencesOptions) {
  if (!metadata) return;

  const language = stringValue(metadata.language);
  if (language) {
    localStorage.setItem("language", language);
    changeLanguage(language);
  }

  const theme = stringValue(metadata.theme);
  if (theme) {
    localStorage.setItem("lambchat-theme", theme);
    dispatchEvent(new CustomEvent("theme:external-change", { detail: theme }));
  }

  if (metadata.theme_schedule !== undefined) {
    localStorage.setItem(
      THEME_SCHEDULE_STORAGE_KEY,
      JSON.stringify(metadata.theme_schedule),
    );
    dispatchEvent(new CustomEvent("theme-schedule:external-change"));
  }

  const fontScale = stringValue(metadata.fontScale);
  if (isFontScale(fontScale)) {
    localStorage.setItem(FONT_SCALE_STORAGE_KEY, fontScale);
    dispatchEvent(
      new CustomEvent(FONT_SCALE_EXTERNAL_CHANGE_EVENT, {
        detail: fontScale,
      }),
    );
  }

  const newlineModifier = stringValue(metadata.newlineModifier);
  if (newlineModifier) {
    localStorage.setItem(NEWLINE_MODIFIER_STORAGE_KEY, newlineModifier);
  }

  const storedThinkingLevel = stringValue(metadata.defaultThinkingLevel);
  if (storedThinkingLevel) {
    // "off" 档已下线：历史存量值归一为最低档，避免把 off 写回本地
    const defaultThinkingLevel = String(
      normalizeThinkingOptionValue(storedThinkingLevel),
    );
    localStorage.setItem(
      DEFAULT_THINKING_LEVEL_STORAGE_KEY,
      defaultThinkingLevel,
    );
    dispatchEvent(
      new CustomEvent("thinking-preference-updated", {
        detail: defaultThinkingLevel,
      }),
    );
  }

  if (metadata.sidebarCollapsed !== undefined) {
    const sidebarCollapsed = String(metadata.sidebarCollapsed);
    localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, sidebarCollapsed);
    dispatchEvent(
      new CustomEvent("sidebar-collapsed-changed", {
        detail: sidebarCollapsed === "true",
      }),
    );
  }

  if (metadata.projectsCollapsed !== undefined) {
    const projectsCollapsed = String(metadata.projectsCollapsed);
    localStorage.setItem(PROJECTS_COLLAPSED_STORAGE_KEY, projectsCollapsed);
    dispatchEvent(
      new CustomEvent("projects-collapsed-changed", {
        detail: projectsCollapsed === "true",
      }),
    );
  }

  if (metadata.chatsCollapsed !== undefined) {
    const chatsCollapsed = String(metadata.chatsCollapsed);
    localStorage.setItem(CHATS_COLLAPSED_STORAGE_KEY, chatsCollapsed);
    dispatchEvent(
      new CustomEvent("chats-collapsed-changed", {
        detail: chatsCollapsed === "true",
      }),
    );
  }

  if (metadata.scheduledTasksCollapsed !== undefined) {
    const scheduledTasksCollapsed = String(metadata.scheduledTasksCollapsed);
    localStorage.setItem(
      SCHEDULED_TASKS_COLLAPSED_STORAGE_KEY,
      scheduledTasksCollapsed,
    );
    dispatchEvent(
      new CustomEvent("scheduled-tasks-collapsed-changed", {
        detail: scheduledTasksCollapsed === "true",
      }),
    );
  }

  const defaultModelId = stringValue(metadata.defaultModelId);
  const defaultModel = stringValue(metadata.defaultModel);
  if (defaultModelId || defaultModel) {
    if (defaultModelId) {
      localStorage.setItem(DEFAULT_MODEL_ID_STORAGE_KEY, defaultModelId);
    }
    if (defaultModel) {
      localStorage.setItem(DEFAULT_MODEL_STORAGE_KEY, defaultModel);
    }
    dispatchEvent(
      new CustomEvent("model-preference-updated", {
        detail: {
          modelId: defaultModelId ?? "",
          modelValue: defaultModel ?? "",
        },
      }),
    );
  }
}
