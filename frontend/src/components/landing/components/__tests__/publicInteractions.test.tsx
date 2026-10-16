/** @vitest-environment jsdom */
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ScreenshotCard } from "../ScreenshotCard";
import { InterfaceSection } from "../InterfaceSection";
import { DashboardSection } from "../DashboardSection";
import { ResponsiveSection } from "../ResponsiveSection";
import {
  MAIN_SHOTS,
  MGMT_SHOTS,
  RESPONSIVE_SHOTS,
  themedShots,
} from "../../data";
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../../../chat/ChatMessage/ImageWithSkeleton", () => ({
  ImageWithSkeleton: ({ src, alt }: { src: string; alt: string }) => (
    <img src={src} alt={alt} />
  ),
}));
afterEach(cleanup);
test("screenshot preview is a named native button and opens the selected image", () => {
  const open = vi.fn();
  render(
    <ScreenshotCard src="/demo.webp" alt="Agent workspace" onClick={open} />,
  );
  const button = screen.getByRole("button", { name: "Agent workspace" });
  expect(button.getAttribute("type")).toBe("button");
  fireEvent.click(button);
  expect(open).toHaveBeenCalledOnce();
});

test.each([
  [InterfaceSection, MAIN_SHOTS],
  [DashboardSection, MGMT_SHOTS],
  [ResponsiveSection, RESPONSIVE_SHOTS],
] as const)(
  "theme changes preserve screenshot cards observed by scroll reveal",
  (Section, shots) => {
    const open = vi.fn();
    const { rerender } = render(<Section shots={shots} onOpenViewer={open} />);
    const label = `landing.${shots[0].altKey}`;
    const card = screen.getByRole("button", { name: label });
    const darkShots = themedShots(shots, "dark");
    rerender(<Section shots={darkShots} onOpenViewer={open} />);
    expect(screen.getByRole("button", { name: label })).toBe(card);
    expect(screen.getByAltText(label).getAttribute("src")).toBe(
      darkShots[0].src,
    );
    fireEvent.click(card);
    expect(open).toHaveBeenCalledWith(darkShots[0].src, label);
  },
);
