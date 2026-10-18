/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { MarkAllReadBadge } from "../MarkAllReadBadge";

afterEach(cleanup);

function show(loading = false) {
  const mark = vi.fn();
  const open = vi.fn();
  const parentKey = vi.fn();
  const view = render(
    <button
      type="button"
      aria-label="Open group"
      onClick={open}
      onKeyDown={parentKey}
    >
      <MarkAllReadBadge
        count={3}
        badgeId="group"
        markingReadId={loading ? "group" : null}
        onMarkAllRead={mark}
        tooltip="Mark all read"
      />
    </button>,
  );
  return {
    ...view,
    mark,
    open,
    parentKey,
    trigger: screen.getByRole("button", { name: "Mark all read" }),
  };
}

test("the activation target contains a separate small visual badge without nesting native buttons", () => {
  const { container, trigger, mark, open } = show();
  expect(trigger.tagName).toBe("SPAN");
  expect(container.querySelectorAll("button")).toHaveLength(1);
  expect(screen.getByText("3")).not.toBe(trigger);
  fireEvent.click(trigger);
  expect(mark).toHaveBeenCalledTimes(1);
  expect(open).not.toHaveBeenCalled();
});

test.each(["Enter", " "])(
  "%s marks the group read without activating its parent",
  (key) => {
    const { trigger, mark, open, parentKey } = show();
    expect(fireEvent.keyDown(trigger, { key })).toBe(false);
    expect(mark).toHaveBeenCalledTimes(1);
    expect(open).not.toHaveBeenCalled();
    expect(parentKey).not.toHaveBeenCalled();
  },
);

test.each(["click", "Enter", " "])(
  "a pending mark-read action rejects another %s activation",
  (kind) => {
    const { trigger, mark, open, parentKey } = show(true);
    expect(trigger).toHaveAttribute("aria-disabled", "true");
    if (kind === "click") fireEvent.click(trigger);
    else expect(fireEvent.keyDown(trigger, { key: kind })).toBe(false);
    expect(mark).not.toHaveBeenCalled();
    expect(open).not.toHaveBeenCalled();
    expect(parentKey).not.toHaveBeenCalled();
  },
);
