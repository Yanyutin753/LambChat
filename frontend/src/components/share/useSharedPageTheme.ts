import { useEffect, useState } from "react";
import {
  applyThemeToDocument,
  getInitialThemePreference,
  resolveNextTheme,
  THEME_STORAGE_KEY,
  type Theme,
} from "../../utils/themeDom";

// Theme management for shared pages (independent of main app context).
// Cycles light -> dark -> sepia like the main app and fully replaces the
// theme classes on <html>, so a stale theme-sepia left by the boot script
// cannot trap the page in eye-care mode.
export function useSharedPageTheme() {
  const [theme, setTheme] = useState<Theme>(getInitialThemePreference);

  useEffect(() => {
    applyThemeToDocument(theme);
    localStorage.setItem(THEME_STORAGE_KEY, theme);
    // Shared routes render inside the ambient ThemeProvider; keep its state in
    // sync so in-app navigation back to the main app does not show a stale theme.
    window.dispatchEvent(
      new CustomEvent("theme:external-change", { detail: theme }),
    );
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => resolveNextTheme(prev));
  };

  return { theme, toggleTheme };
}
