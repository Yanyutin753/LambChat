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

/** 主题循环快捷键（Ctrl/Cmd+Shift+L）；可编辑目标的豁免由监听方负责 */
export function isThemeCycleShortcut(
  event: Pick<KeyboardEvent, "key" | "ctrlKey" | "metaKey" | "shiftKey">,
): boolean {
  return (
    (event.ctrlKey || event.metaKey) &&
    event.shiftKey &&
    (event.key === "L" || event.key === "l")
  );
}

export function resolveNextTheme(current: Theme): Theme {
  const index = THEME_CYCLE.indexOf(current);
  return THEME_CYCLE[(index + 1) % THEME_CYCLE.length] ?? "light";
}

/** 按时段自动切换主题的偏好（与后端 metadata 校验同构） */
export interface ThemeSchedule {
  enabled: boolean;
  /** 夜间开始 HH:MM */
  start: string;
  /** 夜间结束 HH:MM */
  end: string;
  /** 夜间使用的主题（暗色或护眼） */
  nightTheme: "dark" | "sepia";
}

const THEME_SCHEDULE_STORAGE_KEY = "lambchat-theme-schedule";

export const THEME_SCHEDULE_KEY = THEME_SCHEDULE_STORAGE_KEY;

export const THEME_SCHEDULE_CHANGE_EVENT = "theme-schedule-change";

const TIME_PATTERN = /^([01]\d|2[0-3]):[0-5]\d$/;

function toMinutes(time: string): number {
  const [hours, minutes] = time.split(":").map(Number);
  return hours * 60 + minutes;
}

/** 校验并归一 themeSchedule；不合式返回 null（与后端拒绝规则一致） */
export function parseThemeSchedule(value: unknown): ThemeSchedule | null {
  if (typeof value !== "object" || value === null) return null;
  const record = value as Record<string, unknown>;
  const { enabled, start, end, nightTheme } = record;
  if (typeof enabled !== "boolean") return null;
  if (typeof start !== "string" || !TIME_PATTERN.test(start)) return null;
  if (typeof end !== "string" || !TIME_PATTERN.test(end)) return null;
  if (nightTheme !== "dark" && nightTheme !== "sepia") return null;
  return { enabled, start, end, nightTheme };
}

/** 定时主题解析：夜窗内返回 nightTheme，否则 light；起止相同视为无效配置 */
export function resolveScheduledTheme(
  nowMinutes: number,
  schedule: ThemeSchedule,
): Theme {
  const start = toMinutes(schedule.start);
  const end = toMinutes(schedule.end);
  if (start === end) return "light";
  const inNight =
    start < end ? nowMinutes >= start && nowMinutes < end : nowMinutes >= start || nowMinutes < end;
  return inNight ? schedule.nightTheme : "light";
}

/** 读取当前时刻的本地分钟数（0..1439），便于注入假时钟测试 */
export function currentLocalMinutes(date: Date = new Date()): number {
  return date.getHours() * 60 + date.getMinutes();
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
