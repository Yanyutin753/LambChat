/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { FormField } from "../ui/FormField";
import { Input } from "../ui/Input";
import { Textarea } from "../ui/Textarea";

afterEach(cleanup);

test("field labels name inputs even when tag previews are siblings", () => {
  render(
    <FormField label="Tags" hint="Separate with commas">
      <Input />
      <div>Research</div>
    </FormField>,
  );
  const input = screen.getByRole("textbox", { name: "Tags" });
  expect(
    document.getElementById(input.getAttribute("aria-describedby")!)
      ?.textContent,
  ).toBe("Separate with commas");
});

test("field errors identify the invalid control and preserve an existing id", () => {
  render(
    <FormField label="Description" error="Required">
      <Textarea id="description" />
    </FormField>,
  );
  const input = screen.getByRole("textbox", { name: "Description" });
  expect(input.id).toBe("description");
  expect(input.getAttribute("aria-invalid")).toBe("true");
  expect(
    document.getElementById(input.getAttribute("aria-describedby")!)
      ?.textContent,
  ).toBe("Required");
});

test("wrapping controls preserves their own invalid state", () => {
  render(
    <FormField label="Name">
      <Input error />
    </FormField>,
  );
  expect(
    screen.getByRole("textbox", { name: "Name" }).getAttribute("aria-invalid"),
  ).toBe("true");
});
