/** @vitest-environment jsdom */

import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

const listSettings = vi.fn();
let accessToken: string | null = "token-one";

vi.mock("../../services/api", () => ({
  settingsApi: {
    list: (...args: unknown[]) => listSettings(...args),
    update: vi.fn(),
    reset: vi.fn(),
    resetAll: vi.fn(),
  },
  getAccessToken: () => accessToken,
}));

import { useSettings } from "../useSettings";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

beforeEach(() => {
  accessToken = "token-one";
  listSettings.mockReset();
});

test("coalesces repeated login refreshes while the same token request is pending", async () => {
  const pending = deferred<{ settings: Record<string, never[]> }>();
  listSettings.mockReturnValue(pending.promise);
  renderHook(() => useSettings());

  await waitFor(() => expect(listSettings).toHaveBeenCalledTimes(1));
  act(() => {
    window.dispatchEvent(new CustomEvent("auth:login"));
    window.dispatchEvent(new CustomEvent("auth:login"));
  });

  expect(listSettings).toHaveBeenCalledTimes(1);
  pending.resolve({ settings: {} });
});

test("an older authentication generation cannot overwrite a newer login", async () => {
  const oldRequest = deferred<{
    settings: { frontend: { key: string; value: string }[] };
  }>();
  const newRequest = deferred<{
    settings: { frontend: { key: string; value: string }[] };
  }>();
  listSettings
    .mockReturnValueOnce(oldRequest.promise)
    .mockReturnValueOnce(newRequest.promise);
  const { result } = renderHook(() => useSettings());

  await waitFor(() => expect(listSettings).toHaveBeenCalledTimes(1));
  act(() => {
    accessToken = null;
    window.dispatchEvent(new CustomEvent("auth:logout"));
    accessToken = "token-two";
    window.dispatchEvent(new CustomEvent("auth:login"));
  });
  await waitFor(() => expect(listSettings).toHaveBeenCalledTimes(2));

  await act(async () => {
    newRequest.resolve({
      settings: { frontend: [{ key: "source", value: "new" }] },
    });
    await newRequest.promise;
  });
  await act(async () => {
    oldRequest.resolve({
      settings: { frontend: [{ key: "source", value: "old" }] },
    });
    await oldRequest.promise;
  });

  expect(result.current.settings?.settings.frontend?.[0]?.value).toBe("new");
});
