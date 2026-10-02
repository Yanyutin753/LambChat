/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ToolArgsDisplay } from "../ToolArgsDisplay";
import { ToolArgsBlock } from "../items/ToolArgsBlock";
const copy = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
vi.mock("../../../../utils/clipboard", () => ({ copyToClipboard: copy }));
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

test("argument values use the shared named copy action and preserve undefined", async () => {
  render(<ToolArgsDisplay args={{ query: undefined }} />);
  fireEvent.click(
    screen.getByRole("button", { name: "chat.message.copyArgument" }),
  );
  await waitFor(() => expect(copy).toHaveBeenCalledWith("undefined"));
});

test("complex argument expansion has one owner and copying never toggles it", async () => {
  const { container } = render(
    <ToolArgsDisplay args={{ options: { depth: 3 } }} />,
  );
  expect(container.querySelector('[role="button"] button')).toBeNull();
  const expand = screen.getByRole("button", { name: /common.expand/ });
  expect(expand).toHaveAttribute("aria-expanded", "false");
  fireEvent.click(
    screen.getByRole("button", { name: "chat.message.copyArgument" }),
  );
  await waitFor(() => expect(copy).toHaveBeenCalledWith('{"depth":3}'));
  expect(expand).toHaveAttribute("aria-expanded", "false");
  fireEvent.click(expand);
  expect(expand).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByText(/"depth": 3/)).toBeInTheDocument();
});

test("shared argument block copying does not activate its parent", async () => {
  const activate = vi.fn();
  render(
    <div onClick={activate}>
      <ToolArgsBlock size="detail" copyText="report.md">
        report.md
      </ToolArgsBlock>
    </div>,
  );
  fireEvent.click(screen.getByRole("button", { name: "chat.message.copy" }));
  await waitFor(() => expect(copy).toHaveBeenCalledWith("report.md"));
  expect(activate).not.toHaveBeenCalled();
});
