/** @vitest-environment jsdom */

import { useCallback, useEffect, useMemo, useState } from "react";
import { act, render } from "@testing-library/react";
import { Virtuoso } from "react-virtuoso";
import { afterEach, describe, expect, test, vi } from "vitest";
import { useMessageScroll } from "../useMessageScroll.hook";
import type { UseMessageScrollReturn } from "../useMessageScroll.hook";
import {
  isSessionRunning,
  shouldShowStreamingFooterSkeleton,
} from "../sessionState";
import type { ConnectionStatus } from "../../../../types";

type HarnessMessage = {
  id: string;
  role: "assistant" | "user";
  isStreaming: boolean;
  parts: [];
  runId: string | null;
};

type HarnessProps = {
  messages: HarnessMessage[];
  connectionStatus: ConnectionStatus;
  isLoading: boolean;
};

let lastScrollApi: UseMessageScrollReturn | null = null;

/**
 * Mirrors ChatView's Virtuoso wiring. The components handed to Virtuoso are
 * memoized the same way ChatView does it, so a skeleton toggle changes the
 * Scroller/Footer component identities exactly like the real chat view.
 */
function CapturingHarness({
  messages,
  connectionStatus,
  isLoading,
}: HarnessProps) {
  const [messageListSessionKey] = useState("session-run");

  const scroll = useMessageScroll(
    messages,
    "session-run",
    null,
    null,
    null,
    false,
    false,
    false,
    1,
    null,
  );
  lastScrollApi = scroll;

  const sessionRunning = isSessionRunning(messages, isLoading);
  const hasVisibleStreamingMessage = messages.some(
    (message) => message.role === "assistant" && message.isStreaming,
  );
  const showStreamingFooterSkeleton = shouldShowStreamingFooterSkeleton({
    connectionStatus,
    sessionRunning,
    messageCount: messages.length,
    hasVisibleStreamingMessage,
  });

  const handleScrollerElementChange =
    scroll.handleVirtuosoScrollerElementChange;
  const footerRef = scroll.messagesEndRef;

  // ChatView keeps the Scroller identity stable (useCallback on the stable
  // element-change callback only) so skeleton toggles can never remount the
  // scroller; only the Footer is recreated with the skeleton flag.
  const virtuosoScrollerComponent = useCallback(
    (
      scrollerProps: React.HTMLAttributes<HTMLDivElement> & {
        children?: React.ReactNode;
        ref?: React.Ref<HTMLDivElement>;
      },
    ) => {
      const { children, ref: vRef, ...props } = scrollerProps;
      return (
        <div
          {...props}
          ref={(el: HTMLDivElement | null) => {
            handleScrollerElementChange(el);
            if (typeof vRef === "function") vRef(el);
            else if (vRef)
              (vRef as React.MutableRefObject<HTMLDivElement | null>).current =
                el;
          }}
        >
          {children}
        </div>
      );
    },
    [handleScrollerElementChange],
  );

  const virtuosoFooterComponent = useCallback(
    () => (
      <>
        {showStreamingFooterSkeleton && <div data-testid="footer-skeleton" />}
        <div ref={footerRef} />
      </>
    ),
    [footerRef, showStreamingFooterSkeleton],
  );

  const virtuosoComponents = useMemo(
    () => ({
      Scroller: virtuosoScrollerComponent,
      Footer: virtuosoFooterComponent,
    }),
    [virtuosoScrollerComponent, virtuosoFooterComponent],
  );

  return (
    <Virtuoso
      key={messageListSessionKey}
      ref={scroll.virtuosoRef}
      data={messages}
      computeItemKey={(_, message) => message.id}
      atBottomStateChange={scroll.handleVirtuosoAtBottomChange}
      components={virtuosoComponents}
      itemContent={(_, message) => <div>{message.id}</div>}
    />
  );
}

function message(id: string, role: "user" | "assistant", isStreaming = false) {
  return { id, role, isStreaming, parts: [] as [], runId: null };
}

describe("run completion keeps the chat scroller mounted", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    lastScrollApi = null;
  });

  test("scroller element survives the completion commit where isLoading is still true", async () => {
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
    window.scrollTo = () => {};

    const currentProps: HarnessProps = {
      messages: [
        message("run-user-1", "user"),
        message("run-assistant-1", "assistant", true),
      ],
      connectionStatus: "connected",
      isLoading: true,
    };
    const listeners: Array<() => void> = [];
    function emit() {
      for (const listener of [...listeners]) listener();
    }

    function Controller() {
      const [, setTick] = useState(0);
      useEffect(() => {
        const bump = () => setTick((t) => t + 1);
        listeners.push(bump);
        return () => {
          const index = listeners.indexOf(bump);
          if (index !== -1) listeners.splice(index, 1);
        };
      }, []);
      return <CapturingHarness {...currentProps} />;
    }

    render(<Controller />);
    const commit = () =>
      act(() => {
        emit();
      });
    await act(async () => {
      await Promise.resolve();
    });

    const scrollerDuringRun = lastScrollApi!.virtuosoScrollerRef.current;
    expect(scrollerDuringRun).not.toBeNull();
    expect(scrollerDuringRun!.isConnected).toBe(true);

    // --- Completion commit: the complete/done SSE event sets
    // isStreaming=false + connectionStatus="disconnected" together, while
    // isLoading stays true until sendMessage's finally runs (after the SSE
    // stream closes). This transiently satisfies every
    // shouldShowStreamingFooterSkeleton condition. ---
    currentProps.messages = [
      message("run-user-1", "user"),
      message("run-assistant-1", "assistant", false),
    ];
    currentProps.connectionStatus = "disconnected";
    commit();

    // The scroller DOM element must NOT be recreated: react-virtuoso remounts
    // the whole scroller subtree (resetting scroll to the first message) when
    // components.Scroller changes identity.
    expect(lastScrollApi!.virtuosoScrollerRef.current).toBe(scrollerDuringRun);
    expect(scrollerDuringRun!.isConnected).toBe(true);

    // --- finally commit: isLoading flips false, skeleton hides again. ---
    currentProps.isLoading = false;
    commit();

    expect(lastScrollApi!.virtuosoScrollerRef.current).toBe(scrollerDuringRun);
    expect(scrollerDuringRun!.isConnected).toBe(true);
  });
});
