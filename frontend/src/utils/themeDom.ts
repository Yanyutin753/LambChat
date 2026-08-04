export type Theme = "light" | "dark";

export const THEME_STORAGE_KEY = "lambchat-theme";

const THEME_COLORS: Record<Theme, string> = {
  light: "#f5f5f4",
  dark: "#151210",
};

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
  return value === "light" || value === "dark";
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
  if (theme === "dark") {
    doc.documentElement.classList.add("dark");
  } else {
    doc.documentElement.classList.remove("dark");
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
