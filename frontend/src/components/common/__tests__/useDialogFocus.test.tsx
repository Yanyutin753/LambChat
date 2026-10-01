/** @vitest-environment jsdom */
import { useRef, useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { ModalSurface } from "../ModalSurface";
import { useDialogFocus } from "../useDialogFocus";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function Drawer() {
  const [open, setOpen] = useState(false);
  const [nested, setNested] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useDialogFocus({ open, onClose: () => setOpen(false), surfaceRef: ref });
  return (
    <>
      <button onClick={() => setOpen(true)}>Open navigation</button>
      <div
        ref={ref}
        role="dialog"
        aria-label="Navigation"
        aria-hidden={!open}
        inert={!open}
        tabIndex={-1}
      >
        <button onClick={() => setOpen(false)}>Close navigation</button>
        <button onClick={() => setNested(true)}>Search</button>
      </div>
      <ModalSurface
        open={nested}
        onClose={() => setNested(false)}
        label="Search dialog"
      >
        <button>Result</button>
      </ModalSurface>
    </>
  );
}

test("mobile drawer traps focus, lets nested dialogs handle Escape, and restores its opener", async () => {
  vi.spyOn(HTMLElement.prototype, "getClientRects").mockReturnValue([
    { width: 44, height: 44 },
  ] as unknown as DOMRectList);
  const user = userEvent.setup();
  render(<Drawer />);
  await user.click(screen.getByRole("button", { name: "Open navigation" }));
  expect(screen.getByRole("dialog", { name: "Navigation" })).toHaveFocus();
  await user.tab({ shift: true });
  expect(
    screen.getByRole("button", { name: "Search", exact: true }),
  ).toHaveFocus();
  await user.tab();
  expect(
    screen.getByRole("button", { name: "Close navigation" }),
  ).toHaveFocus();
  await user.click(screen.getByRole("button", { name: "Search", exact: true }));
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("dialog", { name: "Search dialog" })).toBeNull();
  expect(
    screen.getByRole("dialog", { name: "Navigation" }),
  ).toBeInTheDocument();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("dialog", { name: "Navigation" })).toBeNull();
  expect(screen.getByRole("button", { name: "Open navigation" })).toHaveFocus();
});
