/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ToolArgsBlock } from "../ToolArgsBlock";

const copy = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
vi.mock("../../../../../utils/clipboard", () => ({ copyToClipboard: copy }));
vi.mock("react-hot-toast", () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

test.each(["detail", "compact"] as const)(
  "%s argument block copies the full path without activating its parent",
  async (size) => {
    const path =
      "/workspace/.selected/local-dfd5c55fa4bc4886b24ccd36bc6c76d2/README.md";
    const parentClick = vi.fn();
    render(
      <div onClick={parentClick}>
        <ToolArgsBlock size={size} copyText={path}>
          <span>{path.slice(0, 30)}…</span>
        </ToolArgsBlock>
      </div>,
    );
    fireEvent.click(screen.getByRole("button", { name: "chat.message.copy" }));
    await screen.findByRole("button", { name: "chat.message.copied" });
    expect(copy).toHaveBeenCalledWith(path);
    expect(parentClick).not.toHaveBeenCalled();
  },
);

test("empty arguments keep a disabled copy button", () => {
  render(
    <ToolArgsBlock size="compact" copyText="">
      —
    </ToolArgsBlock>,
  );
  expect(
    screen.getByRole("button", { name: "chat.message.copy" }),
  ).toBeDisabled();
});
