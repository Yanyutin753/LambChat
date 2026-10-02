/** @vitest-environment jsdom */
import { cleanup, render } from "@testing-library/react";
import { act } from "react";
import { afterEach, expect, test } from "vitest";
import { ModalSurface } from "../ModalSurface";

afterEach(cleanup);

function dialogFor(text: string): HTMLElement {
  const dialogs = Array.from(
    document.querySelectorAll<HTMLElement>('[role="dialog"]'),
  );
  const match = dialogs.find((d) => d.textContent?.includes(text));
  if (!match) throw new Error(`dialog containing "${text}" not rendered`);
  return match;
}

test("closing one dialog while opening another keeps focus with the new dialog", async () => {
  const opener = document.createElement("button");
  const root = document.createElement("div");
  root.id = "root";
  Object.defineProperty(root, "inert", {
    configurable: true,
    get: () => root.hasAttribute("inert"),
    set: (value) => root.toggleAttribute("inert", value),
  });
  root.append(opener);
  document.body.append(root);
  opener.focus();

  const { rerender } = render(
    <>
      <ModalSurface open={false} onClose={() => {}}>
        <p>dialog-a</p>
      </ModalSurface>
      <ModalSurface open={false} onClose={() => {}}>
        <p>dialog-b</p>
      </ModalSurface>
    </>,
  );

  // Open A: focus moves into A.
  rerender(
    <>
      <ModalSurface open onClose={() => {}}>
        <p>dialog-a</p>
      </ModalSurface>
      <ModalSurface open={false} onClose={() => {}}>
        <p>dialog-b</p>
      </ModalSurface>
    </>,
  );
  expect(dialogFor("dialog-a")).toBeInTheDocument();
  expect(dialogFor("dialog-a").contains(document.activeElement)).toBe(true);

  // Close A and open B in the same update: B owns focus, A's cleanup must
  // not steal it back after the microtask queue flushes.
  await act(async () => {
    rerender(
      <>
        <ModalSurface open={false} onClose={() => {}}>
          <p>dialog-a</p>
        </ModalSurface>
        <ModalSurface open onClose={() => {}}>
          <p>dialog-b</p>
        </ModalSurface>
      </>,
    );
    await Promise.resolve();
  });

  expect(dialogFor("dialog-b").contains(document.activeElement)).toBe(true);
  root.remove();
});
