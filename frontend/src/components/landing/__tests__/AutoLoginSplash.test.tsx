/** @vitest-environment jsdom */

import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) =>
      key === "landing.autoLoginPending" ? "正在进入 LambChat…" : key,
  }),
}));

import { AutoLoginSplash } from "../AutoLoginSplash";

test("announces auto-login progress politely and keeps the brand visible", () => {
  const { container } = render(<AutoLoginSplash />);

  const status = screen.getByRole("status");
  expect(status.getAttribute("aria-live")).toBe("polite");
  expect(screen.getByText("正在进入 LambChat…")).toBeTruthy();

  // Logo + wordmark stay on screen so the splash reads as the app, not a blank page
  expect(screen.getByAltText("LambChat")).toBeTruthy();
  expect(
    container.querySelector('[data-wordmark-style="text-only"]'),
  ).toBeTruthy();
});

test("renders a custom status text for other auto-login flows", () => {
  render(<AutoLoginSplash text="正在完成登录..." />);

  expect(screen.getByText("正在完成登录...")).toBeTruthy();
  expect(screen.queryByText("正在进入 LambChat…")).toBeNull();
});
