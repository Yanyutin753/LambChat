import { useEffect } from "react";
import { sandboxApi } from "../services/api/sandbox";
import { effectiveApiBase } from "../services/api/serverConfig";
import { getValidAccessToken } from "../services/api/tokenManager";
import {
  daemonProcessStatus,
  readPairingPat,
  restartDaemon,
  savePairing,
} from "../services/tauri/sandboxShell";
import { notifySandboxStatusRefresh } from "./useSandboxStatus";

/** 由桌面壳挂载：登录时配对一次，不依赖设置页，也不在取消配对后持续重连。 */
export function useDesktopAutoPair(userId?: string) {
  useEffect(() => {
    if (!userId) return;
    let cancelled = false;
    let attempts = 0;
    let timer: ReturnType<typeof setTimeout>;
    const pair = async () => {
      attempts += 1;
      try {
        const process = await daemonProcessStatus();
        if (cancelled || process === "unsupported") return;
        const existingPat = await readPairingPat();
        if (cancelled) return;
        if (existingPat) {
          if (process === "running") return;
        } else {
          const jwt = await getValidAccessToken();
          if (cancelled || !jwt) return;
          const pat = await sandboxApi.createPairingPat(jwt);
          if (cancelled) {
            await sandboxApi.revokePairingPat(pat.token);
            return;
          }
          await savePairing({
            serverUrl: effectiveApiBase() || window.location.origin,
            pat: pat.token,
            patId: pat.pat_id,
            confirmPolicy: "all",
          });
        }
        if (cancelled) return;
        await restartDaemon();
        notifySandboxStatusRefresh();
      } catch (error) {
        console.warn("[DesktopAutoPair] pairing failed:", error);
        if (!cancelled && attempts < 3) timer = setTimeout(pair, 3000);
      }
    };
    // 延后一拍，StrictMode 的首次 effect 清理不会重复签发 PAT。
    timer = setTimeout(pair, 0);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [userId]);
}
