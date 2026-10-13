import { describe, expect, it } from "vitest";
import { getSessionTaskIndicator } from "../sessionTaskIndicator";

describe("session task indicator", () => {
  it.each(["queued", "pending", "starting"])("keeps %s visible as work awaiting execution", (status) => {
    expect(getSessionTaskIndicator(status)).toEqual({ kind: "busy", labelKey: "sidebar.pendingStatus" });
  });
  it.each(["running", "recovering"])("keeps %s visible as ongoing work", (status) => {
    expect(getSessionTaskIndicator(status)).toEqual({ kind: "busy", labelKey: "sidebar.runningStatus" });
  });
  it("labels required human input with the existing translated attention label", () => {
    expect(getSessionTaskIndicator("waiting_human")).toEqual({ kind: "attention", labelKey: "sidebar.waitingHuman" });
  });
  it.each([undefined, null, "", "completed", "failed", "cancelled", "expired", "cancelling", "unexpected"])("does not invent active work for %s", (status) => {
    expect(getSessionTaskIndicator(status)).toEqual({ kind: "idle", labelKey: null });
  });
});
