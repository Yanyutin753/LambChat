/** @vitest-environment jsdom */
import { renderHook } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import type { VirtuosoHandle } from "react-virtuoso";
import { useMessageScrollExternalNavigationEffect } from "../useMessageScroll.externalNavigationEffect";

function setup() {
  const scrollToIndex = vi.fn();
  const refs = {
    virtuosoRef: { current: { scrollToIndex } as unknown as VirtuosoHandle },
    virtuosoScrollerRef: { current: document.createElement("div") },
    pendingExternalNavigationRef: { current: null },
    userScrolledUpRef: { current: false }, autoScrollActiveRef: { current: true },
    streamLockActiveRef: { current: true }, pendingHistoryScrollRef: { current: null },
    ignoreProgrammaticScrollUntilRef: { current: 0 }, anchorScrollCleanupRef: { current: null },
    highlightCleanupRef: { current: null }, requestScrollToBottom: vi.fn(),
  };
  const base = { ...refs, externalNavigationTargetRunPending: false, externalScrollToBottom: true, isLoadingHistory: false };
  return { scrollToIndex, base };
}
const message = (run: string) => ({ id: run, role: "assistant" as const, runId: run, isStreaming: false, parts: [] });

test("notification target stays pending before its exact-run history request starts", () => {
  const { scrollToIndex, base } = setup();
  const messages = [message("latest")];
  const { rerender } = renderHook(useMessageScrollExternalNavigationEffect, { initialProps: { ...base, messages, externalNavigationToken: "nav1", externalNavigationTargetRunId: "old" } });
  rerender({ ...base, messages: [message("old"), ...messages], externalNavigationToken: "nav1", externalNavigationTargetRunId: "old" });
  expect(scrollToIndex).toHaveBeenCalledWith(expect.objectContaining({ index: 0, align: "center" }));
});

test("clicking the same loaded run again repositions using the new navigation token", () => {
  const { scrollToIndex, base } = setup();
  const messages = [message("old"), message("latest")];
  const { rerender } = renderHook(useMessageScrollExternalNavigationEffect, { initialProps: { ...base, messages, externalNavigationToken: "nav1", externalNavigationTargetRunId: "old" } });
  expect(scrollToIndex).toHaveBeenCalledOnce();
  rerender({ ...base, messages, externalNavigationToken: "nav2", externalNavigationTargetRunId: "old" });
  expect(scrollToIndex).toHaveBeenCalledTimes(2);
});
