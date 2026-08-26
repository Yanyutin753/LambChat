/** 自动执行模式的 localStorage 持久化状态。 */

import { useEffect, useState } from "react";

export function useAutoModeSetting() {
  const [autoModeEnabled, setAutoModeEnabled] = useState(() => {
    try {
      return localStorage.getItem("lamb-chat-auto-mode") === "true";
    } catch {
      return false;
    }
  });

  // Persist autoModeEnabled to localStorage
  useEffect(() => {
    try {
      localStorage.setItem("lamb-chat-auto-mode", String(autoModeEnabled));
    } catch {
      /* storage unavailable */
    }
  }, [autoModeEnabled]);

  return [autoModeEnabled, setAutoModeEnabled] as const;
}
