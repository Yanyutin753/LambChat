/** @vitest-environment jsdom */
import { expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { createPortal } from "react-dom";
import { useExpandedComposerHost } from "../chatInputExpandedHost";

test("composer remains visible when its slot is replaced", () => {
  function Composer({ generation }: { generation: number }) {
    const { host, slotRef } = useExpandedComposerHost(false, () => {});
    return (
      <>
        <div key={generation} ref={slotRef} />
        {host &&
          createPortal(
            <textarea aria-label="draft" defaultValue="keep me" />,
            host,
          )}
      </>
    );
  }
  const { rerender, unmount } = render(<Composer generation={0} />);
  const input = screen.getByRole("textbox");
  rerender(<Composer generation={1} />);
  expect(screen.getByRole("textbox")).toBe(input);
  expect(input).toHaveValue("keep me");
  unmount();
});

test("expanding and collapsing preserve focus and the selected draft text", () => {
  function Composer({ expanded }: { expanded: boolean }) {
    const { host, slotRef } = useExpandedComposerHost(expanded, () => {});
    return (
      <>
        <div ref={slotRef} />
        {host &&
          createPortal(
            <textarea aria-label="moving draft" defaultValue="keep typing" />,
            host,
          )}
      </>
    );
  }
  const { rerender, unmount } = render(<Composer expanded={false} />);
  const input = screen.getByRole("textbox", {
    name: "moving draft",
  }) as HTMLTextAreaElement;
  input.focus();
  input.setSelectionRange(2, 6, "backward");
  for (const expanded of [true, false]) {
    rerender(<Composer expanded={expanded} />);
    expect(document.activeElement).toBe(input);
    expect([
      input.selectionStart,
      input.selectionEnd,
      input.selectionDirection,
    ]).toEqual([2, 6, "backward"]);
  }
  unmount();
});

test("moving a rich editor preserves backward selection without stealing outside focus", () => {
  function Composer({ expanded }: { expanded: boolean }) {
    const { host, slotRef } = useExpandedComposerHost(expanded, () => {});
    return (
      <>
        <button>outside</button>
        <div ref={slotRef} />
        {host &&
          createPortal(
            <div
              role="textbox"
              contentEditable
              suppressContentEditableWarning
              tabIndex={0}
            >
              keep typing
            </div>,
            host,
          )}
      </>
    );
  }
  const { rerender, unmount } = render(<Composer expanded={false} />);
  const input = screen.getByRole("textbox");
  const text = input.firstChild!;
  input.focus();
  window.getSelection()!.setBaseAndExtent(text, 6, text, 2);
  rerender(<Composer expanded={true} />);
  expect(document.activeElement).toBe(input);
  expect(window.getSelection()!.toString()).toBe("ep t");
  expect(window.getSelection()!.anchorOffset).toBe(6);
  expect(window.getSelection()!.focusOffset).toBe(2);
  const outside = screen.getByRole("button");
  outside.focus();
  rerender(<Composer expanded={false} />);
  expect(document.activeElement).toBe(outside);
  unmount();
});
