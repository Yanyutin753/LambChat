/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { Plus, ChevronDown } from "lucide-react";
import { InteractiveIcon } from "../InteractiveIcon";

const animation = vi.hoisted(() => ({ start: vi.fn(), stop: vi.fn() }));
vi.mock("@animateicons/react/lucide/plus-icon", async () => {
  const { forwardRef, useImperativeHandle, createElement } = await import(
    "react"
  );
  return {
    PlusIcon: forwardRef((_, ref) => {
      useImperativeHandle(ref, () => ({
        startAnimation: animation.start,
        stopAnimation: animation.stop,
      }));
      return createElement("svg");
    }),
  };
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

test("whole-button hover, click and keyboard focus animate without replacing the action", () => {
  const click = vi.fn();
  render(
    <button onClick={click}>
      Add
      <InteractiveIcon>
        <Plus size={16} />
      </InteractiveIcon>
    </button>,
  );
  const button = screen.getByRole("button", { name: "Add" });
  expect(button.querySelector("svg.lucide-plus")).not.toBeNull();
  fireEvent.mouseEnter(button);
  fireEvent.focusIn(button);
  fireEvent.click(button);
  expect(animation.start).toHaveBeenCalledTimes(3);
  expect(click).toHaveBeenCalledOnce();
  fireEvent.mouseLeave(button);
  expect(animation.stop).toHaveBeenCalledOnce();
});

test("disabled actions do not start animations", () => {
  render(
    <button disabled>
      Add
      <InteractiveIcon>
        <Plus />
      </InteractiveIcon>
    </button>,
  );
  fireEvent.mouseEnter(screen.getByRole("button", { name: "Add" }));
  expect(animation.start).not.toHaveBeenCalled();
});

test("rotating state arrows and non-icon content keep their original rendering", () => {
  const { container } = render(
    <InteractiveIcon>
      <ChevronDown className="rotate-180" />
      <img alt="Model" src="/model.svg" />
    </InteractiveIcon>,
  );
  expect(container.querySelector(".rotate-180")).toBeInTheDocument();
  expect(screen.getByAltText("Model")).toBeInTheDocument();
  expect(container.querySelector("[data-interactive-icon]")).toBeNull();
});
