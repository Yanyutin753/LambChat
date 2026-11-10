/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ActivityRailButton } from "../ActivityRailButton";

afterEach(cleanup);

test("a navigation button can use custom artwork and still activate its destination", () => {
  const onClick = vi.fn();
  render(
    <ActivityRailButton aria-label="Companions" onClick={onClick}>
      <span aria-hidden="true">Colored artwork</span>
    </ActivityRailButton>,
  );
  const button = screen.getByRole("button", { name: "Companions" });
  expect(button).toHaveTextContent("Colored artwork");
  fireEvent.click(button);
  expect(onClick).toHaveBeenCalledOnce();
});
