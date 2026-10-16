// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { useMentionPopupPlacement } from "../chatInputViewport";

test("mention placement follows viewport events and removes listeners when inactive", () => {
  const element = document.createElement("div");
  const rect = vi
    .spyOn(element, "getBoundingClientRect")
    .mockReturnValue({ left: 20, width: 300, top: 400 } as DOMRect);
  const container = { current: element };
  const { result, rerender, unmount } = renderHook(
    ({ active }) => useMentionPopupPlacement(active, container),
    { initialProps: { active: true } },
  );
  expect(result.current).toMatchObject({ left: 20, width: 300 });
  rect.mockReturnValue({ left: 30, width: 280, top: 420 } as DOMRect);
  act(() => window.dispatchEvent(new Event("resize")));
  expect(result.current).toMatchObject({ left: 30, width: 280 });
  rerender({ active: false });
  expect(result.current).toBeNull();
  rect.mockClear();
  act(() => window.dispatchEvent(new Event("scroll")));
  expect(rect).not.toHaveBeenCalled();
  unmount();
  rect.mockRestore();
});
