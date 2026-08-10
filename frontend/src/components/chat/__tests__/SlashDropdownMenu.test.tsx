/** @vitest-environment jsdom */

import { fireEvent, render, screen } from "@testing-library/react";
import { createRef } from "react";
import { describe, expect, test, vi } from "vitest";
import { SlashDropdownMenu } from "../SlashDropdownMenu";
import {
  CHAT_INPUT_SLASH_COMMANDS,
  getSlashDropdownSections,
  type SlashDropdownItem,
} from "../chatInputSlashCommands";

const item: SlashDropdownItem = {
  type: "command",
  command: CHAT_INPUT_SLASH_COMMANDS[0],
};
const items = [item];
const sections = getSlashDropdownSections(items);
const containerRef = createRef<HTMLDivElement>();

function MenuFixture({
  open,
  onDismiss,
}: {
  open: boolean;
  onDismiss: () => void;
}) {
  return (
    <>
      <button type="button" data-testid="outside">
        Outside
      </button>
      <SlashDropdownMenu
        open={open}
        sections={sections}
        items={items}
        runSkillNameSet={new Set()}
        containerRef={containerRef}
        onApplySelection={vi.fn()}
        highlightIndex={0}
        onHighlightChange={vi.fn()}
        onDismiss={onDismiss}
      />
    </>
  );
}

describe("SlashDropdownMenu outside dismissal", () => {
  test("dismisses on an outside mouse press", () => {
    const onDismiss = vi.fn();
    render(<MenuFixture open onDismiss={onDismiss} />);

    fireEvent.mouseDown(screen.getByTestId("outside"));

    expect(onDismiss).toHaveBeenCalledOnce();
  });

  test("does not dismiss on a mouse press inside the portaled menu", () => {
    const onDismiss = vi.fn();
    render(<MenuFixture open onDismiss={onDismiss} />);

    fireEvent.mouseDown(
      screen.getByRole("listbox", { name: "Slash commands" }),
    );

    expect(onDismiss).not.toHaveBeenCalled();
  });

  test("does not listen while closed or after unmount", () => {
    const whileClosed = vi.fn();
    const closed = render(<MenuFixture open={false} onDismiss={whileClosed} />);

    fireEvent.mouseDown(screen.getByTestId("outside"));
    expect(whileClosed).not.toHaveBeenCalled();
    closed.unmount();

    const afterUnmount = vi.fn();
    const open = render(<MenuFixture open onDismiss={afterUnmount} />);
    open.unmount();
    fireEvent.mouseDown(document.body);

    expect(afterUnmount).not.toHaveBeenCalled();
  });

  test("uses the latest dismissal callback while remaining open", () => {
    const first = vi.fn();
    const latest = vi.fn();
    const view = render(<MenuFixture open onDismiss={first} />);
    view.rerender(<MenuFixture open onDismiss={latest} />);

    fireEvent.mouseDown(screen.getByTestId("outside"));

    expect(first).not.toHaveBeenCalled();
    expect(latest).toHaveBeenCalledOnce();
  });
});
