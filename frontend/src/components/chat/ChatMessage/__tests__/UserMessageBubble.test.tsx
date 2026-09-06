/** @vitest-environment jsdom */

import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("react-i18next", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-i18next")>();
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string) => {
        if (key === "mode.auto") return "自动";
        if (key === "mode.goal") return "目标";
        return key;
      },
    }),
  };
});

import { UserMessageBubble } from "../UserMessageBubble";

test("renders run-mode chips on the user message when modes were active", () => {
  render(<UserMessageBubble content="ok" runModes={["auto", "goal"]} />);

  expect(screen.getByText("ok")).toBeTruthy();
  expect(screen.getByText("自动")).toBeTruthy();
  expect(screen.getByText("目标")).toBeTruthy();
});

test("renders no run-mode chips when the message carries none", () => {
  render(<UserMessageBubble content="ok" />);

  expect(screen.getByText("ok")).toBeTruthy();
  expect(screen.queryByText("自动")).toBeNull();
  expect(screen.queryByText("目标")).toBeNull();
});
