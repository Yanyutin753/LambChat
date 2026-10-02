/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ProfileModelsTab } from "../ProfileModelsTab";
const state = vi.hoisted(() => ({
  availableModels: null as null | [],
  modelsLoading: true,
  modelsError: false,
  reloadModels: vi.fn(),
}));
vi.mock("../../../../contexts/SettingsContext", () => ({
  useSettingsContext: () => state,
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(cleanup);
test("the model catalog shows loading, retryable failure and successful empty separately", () => {
  const { rerender } = render(<ProfileModelsTab />);
  expect(screen.getByRole("status")).toHaveTextContent("common.loading");
  expect(screen.queryByText("profile.noModels")).toBeNull();
  state.modelsLoading = false;
  state.modelsError = true;
  rerender(<ProfileModelsTab />);
  expect(screen.getByRole("alert")).toHaveTextContent("common.loadFailed");
  expect(screen.queryByText("profile.noModels")).toBeNull();
  fireEvent.click(
    screen.getByRole("button", { name: "common.retry: nav.models" }),
  );
  expect(state.reloadModels).toHaveBeenCalledOnce();
  state.modelsError = false;
  state.availableModels = [];
  rerender(<ProfileModelsTab />);
  expect(screen.getByText("profile.noModels")).toBeTruthy();
});
