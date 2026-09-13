import {
  createContext,
  useContext,
  useEffect,
  useLayoutEffect,
  useState,
  type ReactNode,
} from "react";
import { authApi } from "../services/api";
import { useThemeShortcut } from "../hooks/useThemeShortcut";
import {
  applyThemeToDocument,
  currentLocalMinutes,
  getInitialThemePreference,
  isTheme,
  parseThemeSchedule,
  resolveNextTheme,
  resolveScheduledTheme,
  THEME_SCHEDULE_CHANGE_EVENT,
  THEME_SCHEDULE_KEY,
  THEME_STORAGE_KEY,
  type Theme,
  type ThemeSchedule,
} from "../utils/themeDom";

interface ThemeContextType {
  theme: Theme;
  toggleTheme: () => void;
  setTheme: (theme: Theme) => void;
  themeSchedule: ThemeSchedule | null;
  /** 更新定时切换偏好；null 表示未配置。手动切主题会自动退出自动模式。 */
  setThemeSchedule: (schedule: ThemeSchedule | null) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

interface ThemeProviderProps {
  children: ReactNode;
}

export function ThemeProvider({ children }: ThemeProviderProps) {
  const [theme, setThemeState] = useState<Theme>(getInitialThemePreference);
  const [themeSchedule, setScheduleState] = useState<ThemeSchedule | null>(() => {
    try {
      const raw = localStorage.getItem(THEME_SCHEDULE_KEY);
      return raw ? parseThemeSchedule(JSON.parse(raw)) : null;
    } catch {
      return null;
    }
  });

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

  // 按时段自动切换：到点应用定时解析结果（30s 轮询覆盖跨窗口休眠唤醒）
  useEffect(() => {
    if (!themeSchedule?.enabled) return;
    const applyScheduledTheme = () => {
      setThemeState(resolveScheduledTheme(currentLocalMinutes(), themeSchedule));
    };
    applyScheduledTheme();
    const timer = window.setInterval(applyScheduledTheme, 30_000);
    return () => window.clearInterval(timer);
  }, [themeSchedule]);

  // 偏好持久化（与 theme 同模式：变更即写本地并同步后端）
  useEffect(() => {
    if (!themeSchedule) return;
    localStorage.setItem(THEME_SCHEDULE_KEY, JSON.stringify(themeSchedule));
    authApi.updateMetadata({ themeSchedule }).catch(() => {});
  }, [themeSchedule]);

  // Listen for external schedule changes (e.g. from auth login restoring backend preferences)
  useEffect(() => {
    const handleExternalScheduleChange = (e: Event) => {
      setScheduleState(parseThemeSchedule((e as CustomEvent).detail));
    };

    window.addEventListener(
      THEME_SCHEDULE_CHANGE_EVENT,
      handleExternalScheduleChange,
    );
    return () =>
      window.removeEventListener(
        THEME_SCHEDULE_CHANGE_EVENT,
        handleExternalScheduleChange,
      );
  }, []);

  const toggleTheme = () => {
    setThemeState((prev) => resolveNextTheme(prev));
    disableAutoSchedule();
  };

  useThemeShortcut(toggleTheme);

  const setTheme = (newTheme: Theme) => {
    setThemeState(newTheme);
    disableAutoSchedule();
  };

  const disableAutoSchedule = () => {
    setScheduleState((prev) =>
      prev?.enabled ? { ...prev, enabled: false } : prev,
    );
  };

  const setThemeSchedule = (schedule: ThemeSchedule | null) => {
    if (schedule && !parseThemeSchedule(schedule)) return;
    setScheduleState(schedule);
    if (!schedule) {
      try {
        localStorage.removeItem(THEME_SCHEDULE_KEY);
      } catch {
        // Storage can be unavailable in restricted browser contexts.
      }
    }
  };

  return (
    <ThemeContext.Provider
      value={{ theme, toggleTheme, setTheme, themeSchedule, setThemeSchedule }}
    >
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
