/** @vitest-environment jsdom */
import { cleanup, render } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { Plus } from "lucide-react";
import { InteractiveIcon } from "../InteractiveIcon";
import { BackIcon } from "../BackIcon";
import { LoadingSpinner } from "../LoadingSpinner";

afterEach(cleanup);

test.each([
  [16, "1rem"],
  [18, "1.125rem"],
  [undefined, "1.5rem"],
  ["0.875rem", "0.875rem"],
  ["1em", "1em"],
  ["0.82em", "0.82em"],
])("animated icon size %s follows root font size", (size, expected) => {
  const { container } = render(
    <button aria-label="Add">
      <InteractiveIcon>
        <Plus size={size} />
      </InteractiveIcon>
    </button>,
  );
  expect(
    container
      .querySelector<HTMLElement>("[data-interactive-icon]")
      ?.style.getPropertyValue("--interactive-icon-size"),
  ).toBe(expected);
});

test("custom back and loading icons scale at their original relative sizes", () => {
  const { container } = render(
    <>
      <BackIcon size={18} />
      <LoadingSpinner size="sm" />
      <LoadingSpinner size={13} />
    </>,
  );
  expect(
    [...container.querySelectorAll("svg")].map((svg) => [
      svg.getAttribute("width"),
      svg.getAttribute("height"),
    ]),
  ).toEqual([
    ["1.125rem", "1.125rem"],
    ["1rem", "1rem"],
    ["0.8125rem", "0.8125rem"],
  ]);
});
