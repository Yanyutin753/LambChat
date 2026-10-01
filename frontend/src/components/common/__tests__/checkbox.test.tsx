/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { Checkbox } from "../Checkbox";

afterEach(cleanup);

test("checkbox text labels activate the control once", async () => {
  const onChange = vi.fn();
  render(
    <label>
      <Checkbox checked={false} onChange={onChange} />
      Enable account
    </label>,
  );
  await userEvent.click(screen.getByText("Enable account"));
  expect(onChange).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("checkbox", { name: "Enable account" })).toBeTruthy();
});

test("checkboxes support Space and keep activation out of their parent", async () => {
  const onChange = vi.fn();
  const onRowClick = vi.fn();
  render(
    <div onClick={onRowClick}>
      <label>
        <Checkbox checked={false} onChange={onChange} />
        Select result
      </label>
    </div>,
  );
  await userEvent.tab();
  expect(document.activeElement).toBe(
    screen.getByRole("checkbox", { name: "Select result" }),
  );
  await userEvent.keyboard(" ");
  expect(onChange).toHaveBeenCalledTimes(1);
  expect(onRowClick).not.toHaveBeenCalled();
});

test("disabled checkbox labels cannot change their value", async () => {
  const onChange = vi.fn();
  render(
    <label>
      <Checkbox checked disabled onChange={onChange} />
      Locked setting
    </label>,
  );
  expect(
    (
      screen.getByRole("checkbox", {
        name: "Locked setting",
      }) as HTMLInputElement
    ).disabled,
  ).toBe(true);
  await userEvent.click(screen.getByText("Locked setting"));
  expect(onChange).not.toHaveBeenCalled();
});
