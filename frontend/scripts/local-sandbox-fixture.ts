import { resolvePreviewLanguage, translatePreviewText } from "./preview-i18n";
/** Preview-only shell/status seam. No real native actions or API writes. */
import { useCallback, useEffect, useRef, useState } from "react";
import { useSandboxStatus as useRealSandboxStatus } from "../src/hooks/useSandboxStatus";
const params = new URLSearchParams(location.search);
const language = resolvePreviewLanguage(params.get("lang"));
const previewText = (text: string) => translatePreviewText(text, language);
const nativeFixture = location.pathname === "/sandbox-data-preview";
let failedProcess = false;
const nativeFlow = nativeFixture && params.get("native-flow") === "1";
const attempted = new Set<string>();
let running = params.get("shell") === "paired";
let policy = "all";
let reportedPolicy = "all";
let restartContext: "pair" | "policy" | null = null;
async function run(operation: string) {
  if (!nativeFlow) return rejectMutation();
  await new Promise((resolve) => setTimeout(resolve, 1200));
  if (params.get("failure") === operation && !attempted.has(operation)) {
    attempted.add(operation);
    throw new Error(previewText("Preview operation unavailable"));
  }
}
export const isShellAvailable = () =>
  nativeFixture && params.get("shell") !== "web";
export const SANDBOX_STATUS_REFRESH_EVENT = "sandbox-status-refresh";
export const notifySandboxStatusRefresh = () => {};
export async function daemonProcessStatus() {
  await new Promise((resolve) => setTimeout(resolve, 800));
  if (params.get("failure") === "process" && !failedProcess) {
    failedProcess = true;
    throw new Error(previewText("Preview status unavailable"));
  }
  return running ? "running" : "stopped";
}
export const subscribeDaemonStatus = async () => null;
async function rejectMutation() {
  await new Promise((resolve) => setTimeout(resolve, 1200));
  throw new Error(previewText("Native actions disabled in preview"));
}
// Explicit flow uses public placeholders only. No bridge, filesystem or API writes.
export async function savePairing() {
  await run("pair-save");
  restartContext = "pair";
}
export async function restartDaemon() {
  await run(restartContext ? `${restartContext}-restart` : "restart");
  running = true;
  reportedPolicy = policy;
  restartContext = null;
}
export const openLocalPath = (path: string) => run(`open-${path}`);
export async function clearPairing() {
  await run("unpair");
  running = false;
}
export const readPairingPat = async () =>
  nativeFlow ? "preview-only-pat" : null;
export async function writeConfirmPolicy(next: string) {
  await run("policy-save");
  policy = next;
  restartContext = "policy";
}
export const getValidAccessToken = async () => "preview-placeholder";
export const sandboxApi = {
  pairingLogin: async () => {
    await run("pair-login");
    return "preview-placeholder";
  },
  createPairingPat: async () => {
    await run("pair-create");
    return { token: "preview-only-pat", pat_id: "preview-only-id" };
  },
  revokePairingPat: async () => {
    await run("unpair-revoke");
  },
};
export const sandboxApiMachines = {
  updateConfirmPolicy: async () => {
    await run("policy-server");
  },
};
function usePreviewSandboxStatus() {
  const [ready, setReady] = useState(false);
  const [, setVersion] = useState(0);
  const [failed, setFailed] = useState(params.get("failure") === "status");
  const [refreshing, setRefreshing] = useState(false);
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    const timer = setTimeout(() => setReady(true), 800);
    return () => {
      clearTimeout(timer);
      if (refreshTimer.current) clearTimeout(refreshTimer.current);
    };
  }, []);
  const refresh = useCallback(() => {
    if (!failed) {
      setVersion((value) => value + 1);
      return;
    }
    if (refreshTimer.current) return;
    setRefreshing(true);
    refreshTimer.current = setTimeout(() => {
      refreshTimer.current = null;
      setFailed(false);
      setRefreshing(false);
    }, 1200);
  }, [failed]);
  const online = ready && !failed && running;
  return {
    status:
      ready && !failed
        ? {
            online,
            daemon_version: "0.3.0",
            daemon_confirm_policy: reportedPolicy,
          }
        : null,
    statusError: ready && failed ? "failed" : null,
    refreshing,
    online,
    refresh,
    currentMachineId: nativeFlow ? "preview-only-machine" : null,
  };
}
export const useSandboxStatus = nativeFixture
  ? usePreviewSandboxStatus
  : useRealSandboxStatus;
