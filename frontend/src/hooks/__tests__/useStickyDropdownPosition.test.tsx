/** @vitest-environment jsdom */

import { fireEvent, render, screen } from "@testing-library/react";
import { useRef, useState } from "react";
import { test, expect, vi } from "vitest";
import { useStickyDropdownPosition } from "../useStickyDropdownPosition";

function PositionedDropdown() {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const style = useStickyDropdownPosition(triggerRef, open, (rect) => ({
    position: "fixed",
    left: rect.left,
    top: rect.bottom + 8,
  }));

  return (
    <>
      <button ref={triggerRef} type="button" onClick={() => setOpen(true)}>
        Open
      </button>
      {open && (
        <div data-testid="dropdown" style={style}>
          Menu
        </div>
      )}
    </>
  );
}

test("positions an opened dropdown before the next animation frame", () => {
  const raf = vi
    .spyOn(window, "requestAnimationFrame")
    .mockImplementation(() => 1);
  vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => undefined);

  render(<PositionedDropdown />);

  const trigger = screen.getByRole("button", { name: "Open" });
  vi.spyOn(trigger, "getBoundingClientRect").mockReturnValue({
    x: 40,
    y: 60,
    left: 40,
    top: 60,
    right: 120,
    bottom: 92,
    width: 80,
    height: 32,
    toJSON: () => ({}),
  } as DOMRect);

  fireEvent.click(trigger);

  expect(screen.getByTestId("dropdown")).toHaveStyle({
    position: "fixed",
    left: "40px",
    top: "100px",
  });
  expect(raf).not.toHaveBeenCalled();
});
