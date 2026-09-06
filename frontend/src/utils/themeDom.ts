export type Theme = "light" | "dark" | "sepia";

export const THEME_STORAGE_KEY = "lambchat-theme";

/** Class挂在 <html> 上用于激活主题（light 不需要类） */
const THEME_CLASSES: Record<Theme, string> = {
  light: "",
  dark: "dark",
  sepia: "theme-sepia",
};

const THEME_COLORS: Record<Theme, string> = {
  light: "#f5f5f4",
  dark: "#151210",
  sepia: "#f3edde",
};

/** 快捷切换按钮的循环顺序 */
const THEME_CYCLE: readonly Theme[] = ["light", "dark", "sepia"];

interface ThemePreferenceEnvironment {
  localStorage?: Pick<Storage, "getItem"> | null;
  matchMedia?: (query: string) => Pick<MediaQueryList, "matches">;
}

interface ThemeDocument {
  documentElement: {
    classList: Pick<DOMTokenList, "add" | "remove">;
    style?: Pick<CSSStyleDeclaration, "setProperty">;
  };
  body?: {
    style?: Pick<CSSStyleDeclaration, "setProperty">;
  } | null;
  querySelector?: (selector: string) => Pick<Element, "setAttribute"> | null;
  querySelectorAll?: (
    selector: string,
  ) => Iterable<Pick<Element, "setAttribute">>;
}

export function isTheme(value: unknown): value is Theme {
  return value === "light" || value === "dark" || value === "sepia";
}

/** 从 <html> 类名读取当前生效的主题模式（dark 类优先，防残留类误判） */
export function readThemeMode(
  doc: Pick<Document, "documentElement"> = document,
): Theme {
  const classList = doc.documentElement.classList;
  if (classList.contains("dark")) {
    return "dark";
  }
  return classList.contains("theme-sepia") ? "sepia" : "light";
}

/** PNG/Canvas 导出时的背景填充色（sepia 用米黄卡片底，避免导出突兀纯白） */
export function themeExportBackground(theme: Theme): string {
  if (theme === "dark") {
    return "#1c1917";
  }
  return theme === "sepia" ? "#faf6ea" : "#ffffff";
}

/* ── 按时段自动切换（夜间主题）── */

export interface ThemeSchedule {
  enabled: boolean;
  /** 夜间开始，"HH:MM"（含） */
  nightStart: string;
  /** 夜间结束，"HH:MM"（不含） */
  nightEnd: string;
  /** 夜间使用的主题：暗色或护眼 */
  nightTheme: "dark" | "sepia";
}

const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;

export const THEME_SCHEDULE_STORAGE_KEY = "lambchat-theme-schedule";

/** 序列化为后端 metadata / localStorage 的存储形态（snake_case） */
export function serializeThemeSchedule(
  schedule: ThemeSchedule,
): Record<string, unknown> {
  return {
    enabled: schedule.enabled,
    night_start: schedule.nightStart,
    night_end: schedule.nightEnd,
    night_theme: schedule.nightTheme,
  };
}

function toMinutes(hhmm: string): number {
  const [hours, minutes] = hhmm.split(":").map(Number);
  return hours * 60 + minutes;
}

/** 从存储/后端 metadata 的原始值解析定时配置；不合法返回 null（忽略并回落手动主题） */
export function parseThemeSchedule(raw: unknown): ThemeSchedule | null {
  if (typeof raw !== "object" || raw === null) {
    return null;
  }
  const record = raw as Record<string, unknown>;
  const { enabled, night_start, night_end, night_theme } = record;
  if (typeof enabled !== "boolean") {
    return null;
  }
  if (typeof night_start !== "string" || !HHMM.test(night_start)) {
    return null;
  }
  if (typeof night_end !== "string" || !HHMM.test(night_end)) {
    return null;
  }
  if (night_theme !== "dark" && night_theme !== "sepia") {
    return null;
  }
  return {
    enabled,
    nightStart: night_start,
    nightEnd: night_end,
    nightTheme: night_theme,
  };
}

/**
 * 计算定时策略在指定时刻应处的主题；返回 null 表示策略未生效（保持手动主题）。
 * 起点含、终点不含；start > end 视为跨午夜窗口。
 */
export function resolveScheduledTheme(
  schedule: ThemeSchedule,
  now: Date,
): Theme | null {
  if (!schedule.enabled) {
    return null;
  }
  const start = toMinutes(schedule.nightStart);
  const end = toMinutes(schedule.nightEnd);
  if (start === end) {
    return null;
  }
  const current = now.getHours() * 60 + now.getMinutes();
  const inNightWindow =
    start < end
      ? current >= start && current < end
      : current >= start || current < end;
  return inNightWindow ? schedule.nightTheme : "light";
}

export function resolveNextTheme(current: Theme): Theme {
  const index = THEME_CYCLE.indexOf(current);
  return THEME_CYCLE[(index + 1) % THEME_CYCLE.length] ?? "light";
}

export function getInitialThemePreference(
  env: ThemePreferenceEnvironment = globalThis,
): Theme {
  try {
    const stored = env.localStorage?.getItem(THEME_STORAGE_KEY);
    if (isTheme(stored)) {
      return stored;
    }

    if (env.matchMedia?.("(prefers-color-scheme: dark)").matches) {
      return "dark";
    }
  } catch {
    // Storage or matchMedia can be unavailable in restricted browser contexts.
  }

  return "light";
}

export function applyThemeToDocument(
  theme: Theme,
  doc: ThemeDocument = document,
): void {
  for (const className of Object.values(THEME_CLASSES)) {
    if (className) {
      doc.documentElement.classList.remove(className);
    }
  }
  const themeClass = THEME_CLASSES[theme];
  if (themeClass) {
    doc.documentElement.classList.add(themeClass);
  }

  const color = THEME_COLORS[theme];
  const colorScheme = theme === "dark" ? "dark" : "light";

  doc.documentElement.style?.setProperty("background-color", color);
  doc.documentElement.style?.setProperty("color-scheme", colorScheme);
  doc.body?.style?.setProperty("background-color", color);
  doc.body?.style?.setProperty("color-scheme", colorScheme);

  const themeColorMetas = doc.querySelectorAll?.('meta[name="theme-color"]');
  if (themeColorMetas) {
    for (const meta of themeColorMetas) {
      meta.setAttribute("content", color);
    }
  } else {
    doc
      .querySelector?.('meta[name="theme-color"]')
      ?.setAttribute("content", color);
  }

  doc
    .querySelector?.('meta[name="apple-mobile-web-app-status-bar-style"]')
    ?.setAttribute("content", theme === "dark" ? "black" : "default");
}
