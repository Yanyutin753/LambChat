/** @vitest-environment jsdom */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, vi } from "vitest";

vi.mock("react-i18next", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-i18next")>();
  return {
    ...actual,
    useTranslation: () => ({
      t: (_key: string, fallback: string) => fallback,
    }),
  };
});

import { SidebarMarkdownContent } from "../SidebarMarkdownContent";

afterEach(cleanup);

test("lightweight sidebar preview keeps normal reading-area spacing and typography", () => {
  render(
    <SidebarMarkdownContent
      content={"First preview line\nSecond preview line"}
      isStreaming
    />,
  );

  const preview = screen.getByText(/First preview line/);
  expect(preview.closest(".sidebar-reasoning-preview__scroll")).toHaveClass(
    "px-3",
    "pt-2",
    "pb-6",
    "sm:px-4",
    "text-[0.9375rem]",
    "leading-[1.75]",
  );
});

test("completed long reasoning begins at the start and can reveal the full history", () => {
  render(
    <SidebarMarkdownContent
      content={"START " + "review ".repeat(2100) + " END"}
    />,
  );
  expect(screen.getByText(/^START/)).not.toHaveTextContent("END");
  fireEvent.click(screen.getByRole("button", { name: "Expand" }));
  expect(screen.getByText(/START/)).toHaveTextContent("END");
});
