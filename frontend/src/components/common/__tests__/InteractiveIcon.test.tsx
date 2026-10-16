/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { Plus, ChevronDown, Square, Star } from "lucide-react";
import { InteractiveIcon } from "../InteractiveIcon";
import { SidebarToggleIcon } from "../SidebarToggleIcon";

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
vi.mock("@animateicons/react/lucide/panel-left-icon", async () => {
  const { forwardRef, useImperativeHandle, createElement } = await import(
    "react"
  );
  return {
    PanelLeftIcon: forwardRef((_, ref) => {
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
  vi.unstubAllGlobals();
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

test("shared sidebar glyph animates from its button and preserves the toggle", () => {
  const toggle = vi.fn();
  render(
    <button onClick={toggle} aria-label="Toggle sidebar">
      <SidebarToggleIcon />
    </button>,
  );
  const button = screen.getByRole("button", { name: "Toggle sidebar" });
  expect(button.querySelector("svg.lucide-panel-left")).not.toBeNull();
  fireEvent.mouseEnter(button);
  fireEvent.focusIn(button);
  fireEvent.click(button);
  expect(animation.start).toHaveBeenCalledTimes(3);
  expect(toggle).toHaveBeenCalledOnce();
  fireEvent.mouseLeave(button);
  fireEvent.focusOut(button);
  expect(animation.stop).toHaveBeenCalledTimes(2);
});

test("unavailable animation glyphs retain their shape, fill and size", () => {
  const cancel = vi.fn();
  const animate = vi.fn(() => ({ cancel }));
  render(
    <button aria-label="Stop">
      <InteractiveIcon>
        <Square size={16} fill="currentColor" />
      </InteractiveIcon>
    </button>,
  );
  const button = screen.getByRole("button", { name: "Stop" });
  const svg = button.querySelector("svg")!;
  Object.defineProperty(svg, "animate", { value: animate });
  expect(svg.getAttribute("fill")).toBe("currentColor");
  expect(svg.getAttribute("width")).toBe("16");
  fireEvent.mouseEnter(button);
  fireEvent.focusIn(button);
  fireEvent.click(button);
  expect(animate).toHaveBeenCalledTimes(3);
  fireEvent.mouseLeave(button);
  expect(cancel).toHaveBeenCalledTimes(3);
});

test("filled and relative-size icons keep their original SVG inside tab controls", () => {
  const animate = vi.fn();
  render(
    <div role="tab" tabIndex={0} aria-label="Favorite">
      <InteractiveIcon>
        <Star size="1em" fill="currentColor" />
      </InteractiveIcon>
    </div>,
  );
  const tab = screen.getByRole("tab", { name: "Favorite" });
  const svg = tab.querySelector("svg")!;
  Object.defineProperty(svg, "animate", { value: animate });
  expect(svg.getAttribute("width")).toBe("1em");
  expect(svg.getAttribute("fill")).toBe("currentColor");
  fireEvent.focusIn(tab);
  expect(animate).toHaveBeenCalledOnce();
});

test("reduced motion disables both library and fallback animations", () => {
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({ matches: true })),
  );
  const animate = vi.fn();
  render(
    <button aria-label="Reduced">
      <InteractiveIcon>
        <Plus />
        <Square />
      </InteractiveIcon>
    </button>,
  );
  const button = screen.getByRole("button", { name: "Reduced" });
  button
    .querySelectorAll("svg")
    .forEach((svg) =>
      Object.defineProperty(svg, "animate", { value: animate }),
    );
  fireEvent.mouseEnter(button);
  fireEvent.focusIn(button);
  fireEvent.click(button);
  expect(animation.start).not.toHaveBeenCalled();
  expect(animate).not.toHaveBeenCalled();
});
