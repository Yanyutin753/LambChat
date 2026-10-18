/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import {
  CollapsiblePill,
  type CollapsibleStatus,
  type CollapsibleVariant,
} from "../CollapsiblePill";

vi.mock("../InteractiveIcon", () => ({
  InteractiveIcon: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(cleanup);

test("running tools do not append decorative ellipsis to their label", () => {
  const { container } = render(
    <CollapsiblePill
      variant="tool"
      status="loading"
      icon={<span />}
      label="电脑控制 · 检查状态 status"
      animatedDots
    />,
  );
  expect(container.querySelector(".pill-btn__label")).not.toHaveClass(
    "typing-dots",
  );
  expect(screen.getByRole("button")).toHaveTextContent(
    "chat.eventStatus.loading",
  );
});

test.each<CollapsibleStatus>(["loading", "success", "error", "cancelled"])(
  "tool labels and descriptions stay on one line when %s",
  (status) => {
    const { container } = render(
      <CollapsiblePill
        variant="tool"
        status={status}
        icon={<span />}
        label="电脑控制 · 检查状态"
        description="Computer control on machine 7eab7fd04964: session caa18591-2e22-41b9-83e0-3272565181ae"
      />,
    );
    const label = container.querySelector(".pill-btn__label")!;
    const description = label.lastElementChild!;
    for (const node of [label, description]) {
      expect(node).toHaveClass("truncate");
      expect(node).not.toHaveClass("whitespace-normal");
      expect(node).not.toHaveClass("[overflow-wrap:anywhere]");
    }
    expect(label).not.toHaveClass("flex-wrap");
    expect(label.firstElementChild).toHaveClass("max-w-full");
  },
);

for (const variant of [
  "default",
  "tool",
  "thinking",
  "summary",
] satisfies CollapsibleVariant[]) {
  test.each<CollapsibleStatus>([
    "idle",
    "loading",
    "success",
    "error",
    "cancelled",
  ])(
    `${variant} rows omit the status icon and still expand when %s`,
    (status) => {
      const { container } = render(
        <CollapsiblePill
          variant={variant}
          status={status}
          icon={<span />}
          label="Read file"
        >
          <p>Tool result</p>
        </CollapsiblePill>,
      );
      expect(container.querySelector(".pill-btn__status")).toBeNull();
      expect(container.querySelector(".pill-btn__chevron")).not.toBeNull();
      const button = screen.getByRole("button");
      expect(button).toHaveAttribute("data-status", status);
      fireEvent.click(button);
      expect(button).toHaveAttribute("aria-expanded", "true");
      expect(screen.getByText("Tool result")).toBeVisible();
    },
  );
}
