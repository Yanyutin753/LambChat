// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ModelSelector } from "../ModelSelector";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../../../services/api", () => ({ authApi: {} }));
vi.mock("../../common/InteractiveIcon", () => ({
  InteractiveIcon: ({ children }: { children: React.ReactNode }) => children,
}));

afterEach(cleanup);

test("click and touch toggle the dropdown and arrow; hover does not open it", () => {
  render(
    <ModelSelector
      models={[{ id: "glm", value: "glm-5.3", label: "glm-5.3" }]}
      currentModelId="glm"
      onSelectModel={vi.fn()}
    />,
  );
  const trigger = screen.getByRole("button", { name: "glm-5.3" });
  const arrow = trigger.querySelector("svg");

  fireEvent.mouseEnter(trigger);
  expect(trigger).toHaveAttribute("aria-expanded", "false");
  fireEvent.click(trigger);
  expect(trigger).toHaveAttribute("aria-expanded", "true");
  expect(arrow).toHaveClass("rotate-180");
  expect(screen.getByRole("textbox")).toBeInTheDocument();
  fireEvent.click(trigger);
  expect(trigger).toHaveAttribute("aria-expanded", "false");
  expect(arrow).not.toHaveClass("rotate-180");
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();

  // Browsers dispatch one click after a touch gesture.
  fireEvent.touchStart(trigger);
  fireEvent.touchEnd(trigger);
  fireEvent.click(trigger);
  expect(trigger).toHaveAttribute("aria-expanded", "true");
  fireEvent.touchStart(trigger);
  fireEvent.touchEnd(trigger);
  fireEvent.click(trigger);
  expect(trigger).toHaveAttribute("aria-expanded", "false");
  expect(arrow).toHaveClass(
    "transition-transform",
    "motion-reduce:transition-none",
  );
});
