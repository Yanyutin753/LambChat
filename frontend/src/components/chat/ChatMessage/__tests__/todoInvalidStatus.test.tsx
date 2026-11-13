/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import type { TodoItem } from "../../../../types";
import { TodoBlock } from "../TodoBlock";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(cleanup);

test.each([undefined, null, "unknown", "constructor", "__proto__"])(
  "renders historical todos with invalid status %s as pending",
  (status) => {
    render(
      <TodoBlock items={[{ content: "Keep this task", status } as TodoItem]} />,
    );
    expect(screen.getByText("Keep this task")).toBeTruthy();
    expect(screen.getByText(/chat.todo.pending/)).toBeTruthy();
  },
);
