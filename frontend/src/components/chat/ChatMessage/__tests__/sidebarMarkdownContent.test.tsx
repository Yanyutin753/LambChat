/** @vitest-environment jsdom */

import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

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

test("lightweight sidebar preview keeps normal reading-area spacing and typography", () => {
  render(
    <SidebarMarkdownContent
      content={"First preview line\nSecond preview line"}
      isStreaming
    />,
  );

  const preview = screen.getByText(/First preview line/);
  expect(preview).toHaveClass(
    "px-3",
    "pt-2",
    "pb-6",
    "sm:px-4",
    "text-[0.9375rem]",
    "leading-[1.75]",
  );
});
