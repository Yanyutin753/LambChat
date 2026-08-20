import {
  createContext,
  useContext,
  useEffect,
  useLayoutEffect,
  useState,
  type ReactNode,
} from "react";
import { authApi } from "../services/api";
import {
  applyThemeToDocument,
  getInitialThemePreference,
  isTheme,
  resolveNextTheme,
  THEME_STORAGE_KEY,
  type Theme,
} from "../utils/themeDom";

interface ThemeContextType {
  theme: Theme;
  toggleTheme: () => void;
  setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

interface ThemeProviderProps {
  children: ReactNode;
}

export function ThemeProvider({ children }: ThemeProviderProps) {
  const [theme, setThemeState] = useState<Theme>(getInitialThemePreference);

  useLayoutEffect(() => {
    applyThemeToDocument(theme);
  }, [theme]);

  useEffect(() => {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
    // Sync to backend (non-blocking)
    authApi.updateMetadata({ theme }).catch(() => {});
  }, [theme]);

  // Listen for system preference changes
  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const handleChange = (e: MediaQueryListEvent) => {
      const stored = localStorage.getItem(THEME_STORAGE_KEY);
      // Only auto-switch if user hasn't explicitly set a preference
      if (!stored) {
        setThemeState(e.matches ? "dark" : "light");
      }
    };

    mediaQuery.addEventListener("change", handleChange);
    return () => mediaQuery.removeEventListener("change", handleChange);
  }, []);

  // Listen for external theme changes (e.g. from auth login restoring backend preferences)
  useEffect(() => {
    const handleExternalThemeChange = (e: Event) => {
      const newTheme = (e as CustomEvent<string>).detail;
      if (isTheme(newTheme)) {
        setThemeState(newTheme);
      }
    };
    window.addEventListener("theme:external-change", handleExternalThemeChange);
    return () =>
      window.removeEventListener(
        "theme:external-change",
        handleExternalThemeChange,
      );
  }, []);

  const toggleTheme = () => {
    setThemeState((prev) => resolveNextTheme(prev));
  };

  const setTheme = (newTheme: Theme) => {
    setThemeState(newTheme);
  };

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useTheme(): ThemeContextType {
  const context = useContext(ThemeContext);
  if (context === undefined) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  return context;
}
