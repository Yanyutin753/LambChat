/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, expect, test, vi } from "vitest";
import { ConfirmDialog } from "../ConfirmDialog";
afterEach(cleanup);
const props = {
  isOpen: true,
  title: "Delete team",
  message: "This action cannot be undone.",
  confirmText: "Delete",
  cancelText: "Cancel",
  onConfirm: vi.fn(),
  onCancel: vi.fn(),
};

test("opening a destructive confirmation focuses its labelled surface instead of deletion", () => {
  render(<ConfirmDialog {...props} />);
  expect(screen.getByRole("dialog", { name: "Delete team" })).toHaveFocus();
  expect(screen.getByRole("button", { name: "Delete" })).not.toHaveFocus();
});

test("confirmation owns stable focus while loading and rejects dismissal", () => {
  const onCancel = vi.fn();
  function Fixture() {
    const [loading, setLoading] = useState(false);
    return (
      <ConfirmDialog
        {...props}
        loading={loading}
        onCancel={onCancel}
        onConfirm={() => setLoading(true)}
      />
    );
  }
  render(<Fixture />);
  const confirm = screen.getByRole("button", { name: "Delete" });
  confirm.focus();
  fireEvent.click(confirm);
  expect(screen.getByRole("dialog")).toHaveFocus();
  expect(confirm).toBeDisabled();
  expect(confirm).toHaveAttribute("aria-busy", "true");
  expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
  fireEvent.keyDown(document, { key: "Escape" });
  fireEvent.click(document.querySelector("[data-dialog-backdrop]")!);
  expect(onCancel).not.toHaveBeenCalled();
});

test("cancelling restores the opener without confirming", async () => {
  const onConfirm = vi.fn();
  function Fixture() {
    const [open, setOpen] = useState(false);
    return (
      <>
        <button onClick={() => setOpen(true)}>Open</button>
        <ConfirmDialog
          {...props}
          isOpen={open}
          onConfirm={onConfirm}
          onCancel={() => setOpen(false)}
        />
      </>
    );
  }
  render(<Fixture />);
  const opener = screen.getByRole("button", { name: "Open" });
  opener.focus();
  fireEvent.click(opener);
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(opener).toHaveFocus();
  expect(onConfirm).not.toHaveBeenCalled();
});
