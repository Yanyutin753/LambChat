/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { Loading, LoadingSpinner } from "../LoadingSpinner";
import { PanelLoadingState } from "../PanelLoadingState";
import { AutoLoginSplash } from "../../landing/AutoLoginSplash";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: () => "Loading…" }),
}));
afterEach(cleanup);

test("inline loading announces its label once and hides the decorative indicator", () => {
  const { container } = render(<Loading text="Preparing preview" />);
  expect(screen.getByRole("status").textContent).toBe("Preparing preview");
  expect(container.querySelector("svg")?.getAttribute("aria-hidden")).toBe(
    "true",
  );
});

test("unlabelled panel loading still exposes a translated status", () => {
  render(<PanelLoadingState />);
  expect(screen.getByRole("status").getAttribute("aria-label")).toBe(
    "Loading…",
  );
});

test("indicator preserves caller dimensions, color and static feedback", () => {
  const { container } = render(
    <LoadingSpinner size={18} static color="text-current" />,
  );
  const indicator = container.querySelector("svg")!;
  expect(indicator.getAttribute("width")).toBe("18");
  expect(indicator.getAttribute("height")).toBe("18");
  expect(indicator.classList.contains("text-current")).toBe(true);
  expect(indicator.classList.contains("spinner-rotate")).toBe(false);
});

test("explicit caller foreground overrides the shared muted color", () => {
  const { container } = render(
    <LoadingSpinner color="text-current" className="text-theme-text-tertiary" />,
  );
  const indicator = container.querySelector("svg")!;
  expect(indicator.classList.contains("text-current")).toBe(false);
  expect(indicator.classList.contains("text-theme-text-tertiary")).toBe(true);
});

test("login transition shows an animated indicator without a duplicate announcement", () => {
  const { container } = render(<AutoLoginSplash text="正在完成登录" />);
  expect(screen.getAllByRole("status")).toHaveLength(1);
  expect(screen.getByRole("status").textContent).toBe("正在完成登录");
  const indicator = screen.getByRole("status").querySelector(".spinner-rotate");
  expect(indicator).not.toBeNull();
  expect(indicator?.getAttribute("aria-hidden")).toBe("true");
  expect(container.querySelector(".auto-login-splash-brand")).not.toBeNull();
});
