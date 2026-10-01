/** @vitest-environment jsdom */
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ScreenshotCard } from "../ScreenshotCard";
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
