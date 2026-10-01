/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ToggleSwitch } from "../ToggleSwitch";
afterEach(cleanup);
test("a switch inside a form toggles without submitting the form", () => {
  const submit = vi.fn((event: React.FormEvent) => event.preventDefault());
  const toggle = vi.fn();
  render(
    <form onSubmit={submit}>
      <ToggleSwitch enabled onToggle={toggle} ariaLabel="Enabled" />
    </form>,
  );
  const control = screen.getByRole("switch", {
    name: "Enabled",
    checked: true,
  });
  fireEvent.click(control);
  expect(toggle).toHaveBeenCalledOnce();
  expect(submit).not.toHaveBeenCalled();
});
