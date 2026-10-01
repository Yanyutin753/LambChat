/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { ScrollButtons } from "../components/ScrollButtons";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(cleanup);

test("hidden scroll actions leave the accessibility tree and keyboard sequence", async () => {
  const top = vi.fn(),
    bottom = vi.fn();
  const user = userEvent.setup();
  const { rerender } = render(
    <ScrollButtons
      showTop={false}
      showBottom
      onScrollToTop={top}
      onScrollToBottom={bottom}
    />,
  );
  expect(
    screen.queryByRole("button", { name: "common.scrollToTop" }),
  ).toBeNull();
  await user.tab();
  expect(
    screen.getByRole("button", { name: "common.scrollToBottom" }),
  ).toHaveFocus();
  await user.keyboard("{Enter}");
  expect(bottom).toHaveBeenCalledOnce();
  expect(top).not.toHaveBeenCalled();
  rerender(
    <ScrollButtons
      showTop
      showBottom={false}
      onScrollToTop={top}
      onScrollToBottom={bottom}
    />,
  );
  expect(
    screen.queryByRole("button", { name: "common.scrollToBottom" }),
  ).toBeNull();
  expect(
    screen.getByRole("button", { name: "common.scrollToTop" }),
  ).toBeEnabled();
});
