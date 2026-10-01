/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ResourceCardTags } from "../ResourceCardTags";
afterEach(cleanup);
test("extra tags collapse into a count with their full names available", () => {
  render(
    <ResourceCardTags
      tags={["Research", "Engineering", "Writing", "Collaboration", "Planning"]}
    />,
  );
  expect(screen.getByText("Research")).toBeTruthy();
  expect(screen.queryByText("Collaboration")).toBeNull();
  expect(screen.getByText("+2").getAttribute("title")).toBe(
    "Collaboration, Planning",
  );
});
test("visible tags preserve filtering and selected state", () => {
  const toggle = vi.fn();
  render(
    <ResourceCardTags
      tags={["Research", "Engineering"]}
      activeTag="Research"
      onToggle={toggle}
    />,
  );
  const research = screen.getByRole("button", { name: "Research" });
  expect(research.getAttribute("aria-pressed")).toBe("true");
  fireEvent.click(research);
  expect(toggle).toHaveBeenCalledWith("Research");
});
test("collapsed filter tags remain selectable from the count menu", () => {
  const toggle = vi.fn();
  render(
    <ResourceCardTags
      tags={["Research", "Engineering", "Writing", "Collaboration", "Planning"]}
      onToggle={toggle}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "+2", exact: true }));
  fireEvent.click(screen.getByRole("menuitem", { name: "Planning" }));
  expect(toggle).toHaveBeenCalledWith("Planning");
  expect(screen.queryByRole("menu")).toBeNull();
});
