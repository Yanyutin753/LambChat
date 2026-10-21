/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { Tag } from "lucide-react";
import { TagBadge } from "../TagBadge";

afterEach(cleanup);

test("metadata keeps its full label and hides decorative icons from assistive technology", () => {
  const label = "desktop-configuration-with-a-long-unbroken-label";
  const { container } = render(
    <TagBadge icon={<Tag />} title={label}>
      {label}
    </TagBadge>,
  );
  expect(screen.getByText(label)).toBeVisible();
  expect(screen.getByTitle(label)).toHaveTextContent(label);
  expect(
    container.querySelector("svg")?.closest('[aria-hidden="true"]'),
  ).not.toBeNull();
  expect(screen.queryByRole("button")).toBeNull();
});
