/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { MarkdownContent } from "../MarkdownContent";

const preview = vi.hoisted(() => vi.fn());
vi.mock("../items/activeRevealPreviewStore", () => ({
  setActiveRevealPreviewState: preview,
}));
afterEach(cleanup);
beforeEach(() => preview.mockReset());

test.each(["https://example.com", "/api/upload/file/report.webp"])(
  "linked Markdown image preserves a single link owner for %s",
  (href) => {
    render(<MarkdownContent content={`[**![hero](/hero.webp)**](${href})`} />);
    const link = screen.getByRole("link", { name: "hero", exact: true });
    expect(link.querySelector("button")).toBeNull();
    fireEvent.click(link);
    expect(
      screen.queryByRole("dialog", { name: "hero", exact: true }),
    ).not.toBeInTheDocument();
    expect(preview).toHaveBeenCalledTimes(href.startsWith("/api/") ? 1 : 0);
  },
);

test("unlinked Markdown image uses the shared native preview button", () => {
  render(<MarkdownContent content="![hero](/hero.webp)" />);
  const image = screen.getByRole("button", { name: "hero", exact: true });
  fireEvent.click(image);
  expect(
    screen.getByRole("dialog").querySelector('img[src$="/hero.webp"]'),
  ).toBeInTheDocument();
});
