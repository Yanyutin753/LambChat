/** Preview-only shell/status seam. Native mutations always fail without running. */
import { useCallback, useEffect, useState } from "react";
import { useSandboxStatus as useRealSandboxStatus } from "../src/hooks/useSandboxStatus";
const params = new URLSearchParams(location.search);
const nativeFixture = location.pathname === "/sandbox-data-preview";
let failedProcess = false;
export const isShellAvailable = () =>
  nativeFixture && params.get("shell") !== "web";
export const SANDBOX_STATUS_REFRESH_EVENT = "sandbox-status-refresh";
export const notifySandboxStatusRefresh = () => {};
export async function daemonProcessStatus() {
  await new Promise((resolve) => setTimeout(resolve, 800));
  if (params.get("failure") === "process" && !failedProcess) {
    failedProcess = true;
    throw new Error("Preview status unavailable");
  }
  return params.get("shell") === "paired" ? "running" : "stopped";
}
export const subscribeDaemonStatus = async () => null;
async function rejectMutation() {
  await new Promise((resolve) => setTimeout(resolve, 1200));
  throw new Error("Native actions disabled in preview");
}
export const savePairing = rejectMutation;
export const restartDaemon = rejectMutation;
export const openLocalPath = rejectMutation;
export const clearPairing = rejectMutation;
export const readPairingPat = async () => null;
export const writeConfirmPolicy = rejectMutation;
export const getValidAccessToken = async () => "preview-placeholder";
export const sandboxApi = {
  pairingLogin: rejectMutation,
  createPairingPat: rejectMutation,
  revokePairingPat: rejectMutation,
};
export const sandboxApiMachines = { updateConfirmPolicy: rejectMutation };
function usePreviewSandboxStatus() {
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(params.get("failure") === "status");
  useEffect(() => {
    const timer = setTimeout(() => setReady(true), 800);
    return () => clearTimeout(timer);
  }, []);
  const refresh = useCallback(() => setFailed(false), []);
  const online = ready && !failed && params.get("shell") === "paired";
  return {
    status: ready && !failed ? { online, daemon_version: "0.3.0" } : null,
    statusError: ready && failed ? "error" : null,
    online,
    refresh,
    currentMachineId: null,
  };
}
export const useSandboxStatus = nativeFixture
  ? usePreviewSandboxStatus
  : useRealSandboxStatus;
