/** @vitest-environment jsdom */
import { act, renderHook } from "@testing-library/react";
import { useMobileKeyboardAware } from "../useMobileKeyboardAware";

test("auth forms follow global keyboard state including native viewport resizing", async () => {
  const { result, unmount } = renderHook(() => useMobileKeyboardAware());
  try {
    await act(async () => {
      document.documentElement.dataset.mobileKeyboard = "true";
    });
    expect(result.current).toBe(true);
    await act(async () => {
      delete document.documentElement.dataset.mobileKeyboard;
    });
    expect(result.current).toBe(false);
  } finally {
    unmount();
    delete document.documentElement.dataset.mobileKeyboard;
  }
});
