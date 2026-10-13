/** Shared lifecycle labels for sidebar and recent-session indicators. */
export function getSessionTaskIndicator(status: unknown): {
  kind: "busy" | "attention" | "idle";
  labelKey: "sidebar.pendingStatus" | "sidebar.runningStatus" | "sidebar.waitingHuman" | null;
} {
  if (status === "queued" || status === "pending" || status === "starting") return {kind:"busy", labelKey:"sidebar.pendingStatus"};
  if (status === "running" || status === "recovering") return {kind:"busy", labelKey:"sidebar.runningStatus"};
  if (status === "waiting_human") return {kind:"attention", labelKey:"sidebar.waitingHuman"};
  return {kind:"idle", labelKey:null};
}
