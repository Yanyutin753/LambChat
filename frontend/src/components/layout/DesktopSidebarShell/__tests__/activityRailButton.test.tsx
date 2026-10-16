/** @vitest-environment jsdom */
import { forwardRef, useImperativeHandle } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import type { IconHandle } from "@animateicons/react";
import { ActivityRailButton } from "../ActivityRailButton";

afterEach(cleanup);

test("rail icons respond to the whole button and keyboard focus without losing navigation", () => {
  const start = vi.fn();
  const stop = vi.fn();
  const navigate = vi.fn();
  const Icon = forwardRef<IconHandle>((_, ref) => {
    useImperativeHandle(ref, () => ({
      startAnimation: start,
      stopAnimation: stop,
    }));
    return <svg aria-hidden="true" />;
  });
  render(
    <ActivityRailButton aria-label="Files" icon={Icon} onClick={navigate} />,
  );
  const button = screen.getByRole("button", { name: "Files" });
  fireEvent.mouseEnter(button);
  expect(start).toHaveBeenCalled();
  fireEvent.focus(button);
  expect(start).toHaveBeenCalledTimes(2);
  fireEvent.blur(button);
  expect(stop).toHaveBeenCalled();
  fireEvent.click(button);
  expect(navigate).toHaveBeenCalledOnce();
});
