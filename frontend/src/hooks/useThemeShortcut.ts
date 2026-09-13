import { useEffect } from "react";

import { isEditableEventTarget } from "../components/panels/askHumanKeyboardGuard";
import { isThemeCycleShortcut } from "../utils/themeDom";

/**
 * 全局主题循环快捷键（Ctrl/Cmd+Shift+L）。焦点在可编辑目标
 * （输入框、文本域、contenteditable）时不劫持按键。
 */
export function useThemeShortcut(cycleTheme: () => void): void {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (!isThemeCycleShortcut(event)) return;
      if (isEditableEventTarget(event.target)) return;
      event.preventDefault();
      cycleTheme();
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [cycleTheme]);
}
