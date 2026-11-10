/** @vitest-environment jsdom */
import { useState } from "react";
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import type { FeaturePanel } from "../../selectors/FeatureMenu";
import { useChatInputConfiguration } from "../chatInputConfiguration";

afterEach(cleanup);

test.each([false, true])(
  "team shortcut respects configuration lock %s",
  (locked) => {
    const selectTeam = vi.fn();
    const { result, unmount } = renderHook(() => {
      const [panel, setPanel] = useState<FeaturePanel>(null);
      const props = useChatInputConfiguration(
        {
          configurationLocked: locked,
          currentAgent: "team",
          onSelectTeam: selectTeam,
          onSend: vi.fn(),
          onStop: vi.fn(),
          isLoading: false,
        },
        setPanel,
      );
      return { panel, props };
    });
    const press = () => {
      document.dispatchEvent(
        new KeyboardEvent("keydown", {
          key: "t",
          ctrlKey: true,
          metaKey: true,
          cancelable: true,
        }),
      );
    };
    act(press);
    expect(result.current.panel).toBe(locked ? null : "team");
    expect(result.current.props.onSelectTeam).toBe(
      locked ? undefined : selectTeam,
    );
    act(press);
    expect(result.current.panel).toBe(null);
    unmount();
    const event = new KeyboardEvent("keydown", {
      key: "t",
      ctrlKey: true,
      metaKey: true,
      cancelable: true,
    });
    document.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
  },
);
