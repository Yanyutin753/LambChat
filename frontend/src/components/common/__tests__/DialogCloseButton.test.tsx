/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";
import { DialogCloseButton } from "../DialogCloseButton";

afterEach(cleanup);

test("closes by its localized accessible name without submitting the surrounding form", () => {
  const close = vi.fn();
  const submit = vi.fn((event) => event.preventDefault());
  render(
    <form onSubmit={submit}>
      <DialogCloseButton onClick={close} />
    </form>,
  );
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.close") }));
  expect(close).toHaveBeenCalledOnce();
  expect(submit).not.toHaveBeenCalled();
});

test("respects a busy dialog's disabled close action", () => {
  const close = vi.fn();
  render(<DialogCloseButton disabled onClick={close} />);
  const button = screen.getByRole("button", { name: i18n.t("common.close") });
  expect(button).toBeDisabled();
  fireEvent.click(button);
  expect(close).not.toHaveBeenCalled();
});

test("preserves a contextual accessible name for nested previews", () => {
  render(<DialogCloseButton aria-label="Close file preview" onClick={vi.fn()} />);
  expect(screen.getByRole("button", { name: "Close file preview" })).toBeTruthy();
});
