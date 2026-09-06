/** @vitest-environment jsdom */

import { useEffect, useMemo, useRef, useState } from "react";
import { act, render } from "@testing-library/react";
import { Virtuoso } from "react-virtuoso";
import { afterEach, describe, expect, test, vi } from "vitest";
import { useMessageScroll } from "../useMessageScroll.hook";
import type { UseMessageScrollReturn } from "../useMessageScroll.hook";
import { getNextMessageListSessionKey } from "../useMessageScroll.followState";

type HarnessMessage = {
  id: string;
  role: "assistant" | "user";
  isStreaming: boolean;
  parts: [];
  runId: string | null;
};

type HarnessProps = {
  messages: HarnessMessage[];
  sessionId: string | null;
  isLoadingHistory: boolean;
  historyLoadGeneration: number;
};

/**
 * Captures the hook API so the test can inspect refs and dispatch events on
 * the live scroller element across remounts.
 */
let lastScrollApi: UseMessageScrollReturn | null = null;

/**
 * Mirrors ChatView's Virtuoso wiring: the list key is updated one
 * effect-cycle after sessionId changes, the custom Scroller writes the
 * scroller ref, and followOutput is gated by manualDetachFromStreamRef.
 */
function CapturingHarness({
  messages,
  sessionId,
  isLoadingHistory,
  historyLoadGeneration,
}: HarnessProps) {
  const previousSessionIdRef = useRef(sessionId);
  const [messageListSessionKey, setMessageListSessionKey] = useState(
    sessionId ?? "__new_session__",
  );

  const scroll = useMessageScroll(
    messages,
    sessionId,
    null,
    null,
    null,
    false,
    false,
    isLoadingHistory,
    historyLoadGeneration,
    null,
  );
  lastScrollApi = scroll;

  useEffect(() => {
    const previousSessionId = previousSessionIdRef.current;
    previousSessionIdRef.current = sessionId;
    setMessageListSessionKey((previousKey) => {
      const nextKey = getNextMessageListSessionKey({
        previousSessionId,
        sessionId,
        messageCount: messages.length,
        previousKey,
      });
      return nextKey === previousKey ? previousKey : nextKey;
    });
  }, [messages.length, sessionId]);

  const manualDetachFromStreamRef = scroll.manualDetachFromStreamRef;
  const handleScrollerElementChange =
    scroll.handleVirtuosoScrollerElementChange;
  const footerRef = scroll.messagesEndRef;

  const handleFollowOutput = useMemo(() => {
    return (isAtBottom: boolean) => {
      if (isLoadingHistory) return isAtBottom ? ("auto" as const) : false;
      if (manualDetachFromStreamRef.current) return false;
      return isAtBottom ? ("smooth" as const) : false;
    };
  }, [isLoadingHistory, manualDetachFromStreamRef]);

  // ChatView keeps the Scroller component identity stable for the list's
  // lifetime (only the Footer may be recreated), so identity stays stable here
  // across skeleton toggles too.
  const virtuosoComponents = useMemo(
    () => ({
      Scroller: (
        scrollerProps: React.HTMLAttributes<HTMLDivElement> & {
          children?: React.ReactNode;
          ref?: React.Ref<HTMLDivElement>;
        },
      ) => {
        const { children, ref: vRef, ...rest } = scrollerProps;
        return (
          <div
            {...rest}
            ref={(el: HTMLDivElement | null) => {
              handleScrollerElementChange(el);
              if (typeof vRef === "function") vRef(el);
              else if (vRef)
                (
                  vRef as React.MutableRefObject<HTMLDivElement | null>
                ).current = el;
            }}
          >
            {children}
          </div>
        );
      },
      Footer: () => <div ref={footerRef} />,
    }),
    [footerRef, handleScrollerElementChange],
  );

  if (messages.length === 0) {
    return <div data-testid="skeleton" />;
  }

  return (
    <Virtuoso
      key={messageListSessionKey}
      ref={scroll.virtuosoRef}
      data={messages}
      computeItemKey={(_, message) => message.id}
      atBottomStateChange={scroll.handleVirtuosoAtBottomChange}
      followOutput={handleFollowOutput}
      components={virtuosoComponents}
      itemContent={(_, message) => <div>{message.id}</div>}
    />
  );
}

function message(id: string, role: "user" | "assistant", isStreaming = false) {
  return { id, role, isStreaming, parts: [] as [], runId: null };
}

describe("switching into a running session keeps manual scroll control", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    lastScrollApi = null;
  });

  test("wheel-up on the live scroller detaches stream follow after a mid-stream session switch", async () => {
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
    window.scrollTo = () => {};

    // Controller that lets the test drive exact commit sequences.
    const currentProps: HarnessProps = {
      messages: [],
      sessionId: "session-a",
      isLoadingHistory: false,
      historyLoadGeneration: 1,
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

    // --- Session A idle with a finished conversation. ---
    currentProps.messages = [
      message("a-user-1", "user"),
      message("a-assistant-1", "assistant"),
    ];
    commit();

    // --- Sidebar switch to session B whose run is still going. ---
    // loadHistory (handleSelectSession path): setMessages([]) +
    // setIsLoadingHistory(true) + generation bump land in one commit while
    // the sessionId state itself is still "session-a".
    currentProps.messages = [];
    currentProps.isLoadingHistory = true;
    currentProps.historyLoadGeneration = 2;
    commit();

    // Fetch resolves: setSessionId(B) + setMessages(history) land in the
    // SAME commit (loadHistory sets them in one synchronous continuation).
    currentProps.sessionId = "session-b";
    currentProps.messages = [
      message("b-user-1", "user"),
      message("b-assistant-1", "assistant", true),
    ];
    currentProps.isLoadingHistory = false;
    commit();
    // The list key updates one effect-cycle later, remounting Virtuoso
    // without any messages.length change (ChatView behavior).
    await act(async () => {
      await Promise.resolve();
    });

    const liveScroller = lastScrollApi!.virtuosoScrollerRef.current;
    expect(liveScroller).not.toBeNull();

    // Streaming chunks keep the same message count.
    for (let i = 0; i < 2; i += 1) {
      currentProps.messages = [
        message("b-user-1", "user"),
        message("b-assistant-1", "assistant", true),
      ];
      commit();
    }

    // The stream follow is armed (bottom lock active, no detach yet).
    expect(lastScrollApi!.manualDetachFromStreamRef.current).toBe(false);

    // --- User wheels up on the live scroller. ---
    act(() => {
      liveScroller!.dispatchEvent(
        new WheelEvent("wheel", { deltaY: -120, bubbles: true }),
      );
    });

    // The wheel must have detached the stream follow so followOutput stops
    // dragging the view back down while the run continues.
    expect(lastScrollApi!.manualDetachFromStreamRef.current).toBe(true);

    // More chunks arrive; the detach must persist.
    currentProps.messages = [
      message("b-user-1", "user"),
      message("b-assistant-1", "assistant", true),
    ];
    commit();
    expect(lastScrollApi!.manualDetachFromStreamRef.current).toBe(true);
  });
});
