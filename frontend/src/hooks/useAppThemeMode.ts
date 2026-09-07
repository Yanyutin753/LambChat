import { useEffect, useState } from "react";

import { readThemeMode, type Theme } from "../utils/themeDom";

/**
 * 读取当前生效的主题模式（light / dark / sepia），并跟随 <html> 类变化更新。
 * 所有「按主题分支」的渲染逻辑统一走这里，不要各自复制 dark 类检测。
 */
export function useAppThemeMode(): Theme {
  const [mode, setMode] = useState<Theme>(() =>
    typeof document === "undefined" ? "light" : readThemeMode(),
  );

  useEffect(() => {
    const sync = () => setMode(readThemeMode());
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });
    return () => observer.disconnect();
  }, []);

  return mode;
}
