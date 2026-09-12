/** @vitest-environment jsdom */
import { expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { createPortal } from "react-dom";
import { useExpandedComposerHost } from "../chatInputExpandedHost";

test("composer remains visible when its slot is replaced", () => {
  function Composer({ generation }: { generation: number }) {
    const { host, slotRef } = useExpandedComposerHost(false);
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
