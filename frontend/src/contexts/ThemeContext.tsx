import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useState,
  type ReactNode,
} from "react";
import { authApi } from "../services/api";
import { isEditableEventTarget } from "../components/panels/askHumanKeyboardGuard";
import {
  applyThemeToDocument,
  getInitialThemePreference,
  isTheme,
  parseThemeSchedule,
  resolveNextTheme,
  resolveScheduledTheme,
  serializeThemeSchedule,
  THEME_SCHEDULE_STORAGE_KEY,
  THEME_STORAGE_KEY,
  type Theme,
  type ThemeSchedule,
} from "../utils/themeDom";

interface ThemeContextType {
  theme: Theme;
  toggleTheme: () => void;
  setTheme: (theme: Theme) => void;
  /** 按时段自动切换配置；null 表示从未配置 */
  schedule: ThemeSchedule | null;
  setSchedule: (schedule: ThemeSchedule | null) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

function readStoredSchedule(): ThemeSchedule | null {
  try {
    return parseThemeSchedule(
      JSON.parse(localStorage.getItem(THEME_SCHEDULE_STORAGE_KEY) ?? "null"),
    );
  } catch {
    return null;
  }
}

interface ThemeProviderProps {
  children: ReactNode;
}

export function ThemeProvider({ children }: ThemeProviderProps) {
  const [theme, setThemeState] = useState<Theme>(getInitialThemePreference);
  const [schedule, setScheduleState] = useState<ThemeSchedule | null>(
    readStoredSchedule,
  );

  useLayoutEffect(() => {
    applyThemeToDocument(theme);
  }, [theme]);

  useEffect(() => {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
    // Sync to backend (non-blocking)
    authApi.updateMetadata({ theme }).catch(() => {});
  }, [theme]);

  // 按时段自动切换：启用时立即对齐一次，并周期性重估（分钟粒度，30s 轮询足够）
  useEffect(() => {
    if (!schedule?.enabled) return;
    const applyScheduled = () => {
      const target = resolveScheduledTheme(schedule, new Date());
      if (target) {
        setThemeState(target);
      }
    };
    applyScheduled();
    const timer = window.setInterval(applyScheduled, 30_000);
    return () => window.clearInterval(timer);
  }, [schedule]);

  // 定时配置持久化：localStorage 即时镜像 + 后端 metadata 同步（非阻塞）
  useEffect(() => {
    if (schedule === null) {
      localStorage.removeItem(THEME_SCHEDULE_STORAGE_KEY);
      return;
    }
    localStorage.setItem(
      THEME_SCHEDULE_STORAGE_KEY,
      JSON.stringify(serializeThemeSchedule(schedule)),
    );
    authApi
      .updateMetadata({ theme_schedule: serializeThemeSchedule(schedule) })
      .catch(() => {});
  }, [schedule]);

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

  // 登录恢复：后端 metadata 里的 theme_schedule 写入本地后通知此处重读
  useEffect(() => {
    const handleExternalScheduleChange = () => {
      setScheduleState(readStoredSchedule());
    };
    window.addEventListener(
      "theme-schedule:external-change",
      handleExternalScheduleChange,
    );
    return () =>
      window.removeEventListener(
        "theme-schedule:external-change",
        handleExternalScheduleChange,
      );
  }, []);

  // 手动切换即退出定时自动（v1 策略：显式选择优先）
  const exitSchedule = useCallback(() => {
    setScheduleState((prev) =>
      prev?.enabled ? { ...prev, enabled: false } : prev,
    );
  }, []);

  const applyManualCycle = useCallback(() => {
    exitSchedule();
    setThemeState((prev) => resolveNextTheme(prev));
  }, [exitSchedule]);

  // 全局主题快捷键：Ctrl/Cmd+Shift+L 循环 亮色→暗色→护眼；可编辑目标让位原生输入
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "l" && event.key !== "L") return;
      if (!(event.ctrlKey || event.metaKey) || !event.shiftKey) return;
      if (event.altKey) return;
      if (isEditableEventTarget(event.target)) return;
      event.preventDefault();
      applyManualCycle();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [applyManualCycle]);

  const toggleTheme = applyManualCycle;

  const setTheme = (newTheme: Theme) => {
    exitSchedule();
    setThemeState(newTheme);
  };

  return (
    <ThemeContext.Provider
      value={{
        theme,
        toggleTheme,
        setTheme,
        schedule,
        setSchedule: setScheduleState,
      }}
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
