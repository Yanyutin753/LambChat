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
