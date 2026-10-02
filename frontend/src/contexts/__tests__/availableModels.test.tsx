/** @vitest-environment jsdom */
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { SettingsProvider, useSettingsContext } from "../SettingsContext";
const api = vi.hoisted(() => ({
  list: vi.fn(),
  pinned: vi.fn(),
  auth: { isAuthenticated: true, token: "one" },
}));
vi.mock("../../hooks/useAuth", () => ({ useAuth: () => api.auth }));
vi.mock("../../hooks/useSettings", () => ({
  useSettings: () => ({ getBooleanSetting: () => true, savingKeys: new Set() }),
}));
vi.mock("../../services/api", () => ({
  modelApi: {
    listAvailable: api.list,
    getPinnedModelIds: api.pinned,
    updatePinnedModelIds: vi.fn(),
  },
}));
const model = { id: "keep", value: "keep", label: "Retained model" };
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}
beforeEach(() => {
  api.auth = { isAuthenticated: true, token: "one" };
  api.list.mockReset();
  api.pinned.mockReset().mockResolvedValue([]);
});
afterEach(cleanup);
test("model errors stay distinct from an empty catalog and can be retried", async () => {
  api.list
    .mockRejectedValueOnce(new Error("Offline"))
    .mockResolvedValue({ models: [] });
  const { result } = renderHook(useSettingsContext, {
    wrapper: SettingsProvider,
  });
  await waitFor(() => expect(result.current.modelsError).toBe(true));
  expect(result.current.availableModels).toBeNull();
  expect(result.current.modelsLoading).toBe(false);
  act(() => result.current.reloadModels());
  await waitFor(() => expect(result.current.availableModels).toEqual([]));
  expect(result.current.modelsError).toBe(false);
});
test("a failed refresh retains the catalog and configured default", async () => {
  api.list
    .mockResolvedValueOnce({ models: [model], default_model_id: "keep" })
    .mockRejectedValueOnce(new Error("Offline"));
  const { result } = renderHook(useSettingsContext, {
    wrapper: SettingsProvider,
  });
  await waitFor(() => expect(result.current.availableModels).toEqual([model]));
  act(() => result.current.reloadModels());
  await waitFor(() => expect(result.current.modelsError).toBe(true));
  expect(result.current.availableModels).toEqual([model]);
  expect(result.current.systemDefaultModelId).toBe("keep");
});
test("account changes reject obsolete catalog and pin responses", async () => {
  const old = deferred<{ models: (typeof model)[] }>();
  const pins = deferred<string[]>();
  api.list.mockReturnValueOnce(old.promise).mockResolvedValue({ models: [] });
  api.pinned.mockReturnValueOnce(pins.promise).mockResolvedValue([]);
  const { result, rerender } = renderHook(useSettingsContext, {
    wrapper: SettingsProvider,
  });
  expect(result.current.modelsLoading).toBe(true);
  api.auth = { isAuthenticated: true, token: "two" };
  rerender();
  await waitFor(() => expect(result.current.availableModels).toEqual([]));
  await act(async () => {
    old.resolve({ models: [model] });
    pins.resolve(["keep"]);
  });
  expect(result.current.availableModels).toEqual([]);
  expect(result.current.pinnedModelIds).toEqual([]);
  api.auth = { isAuthenticated: false, token: "" };
  rerender();
  expect(result.current.availableModels).toBeNull();
  expect(result.current.modelsLoading).toBe(false);
});

test("a superseded refresh cannot replace the latest catalog", async () => {
  const old = deferred<{ models: (typeof model)[] }>();
  api.list.mockReturnValueOnce(old.promise).mockResolvedValue({ models: [] });
  const { result } = renderHook(useSettingsContext, {
    wrapper: SettingsProvider,
  });
  act(() => result.current.reloadModels());
  await waitFor(() => expect(result.current.availableModels).toEqual([]));
  await act(async () => old.resolve({ models: [model] }));
  expect(result.current.availableModels).toEqual([]);
  expect(result.current.modelsError).toBe(false);
});
