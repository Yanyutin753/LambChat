/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ModalSurface } from "../ModalSurface";
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
test("only the top modal receives Escape", () => {
  const first = vi.fn(),
    second = vi.fn();
  render(
    <>
      <ModalSurface open onClose={first}>
        <button>First</button>
      </ModalSurface>
      <ModalSurface open onClose={second}>
        <button>Second</button>
      </ModalSurface>
    </>,
  );
  fireEvent.keyDown(document, { key: "Escape" });
  expect(second).toHaveBeenCalledOnce();
  expect(first).not.toHaveBeenCalled();
});

test("the dialog has its heading name before receiving initial focus", () => {
  const names: string[] = [];
  const focused = (event: FocusEvent) => {
    const el = event.target as HTMLElement;
    if (el.getAttribute("role") === "dialog") {
      names.push(
        document.getElementById(el.getAttribute("aria-labelledby") ?? "")
          ?.textContent ?? "",
      );
    }
  };
  document.addEventListener("focusin", focused);
  try {
    render(
      <ModalSurface open onClose={() => {}}>
        <h2>Navigation details</h2>
      </ModalSurface>,
    );
    expect(names).toEqual(["Navigation details"]);
  } finally {
    document.removeEventListener("focusin", focused);
  }
});
test("dragging content never dismisses, dragging the handle does", () => {
  vi.useFakeTimers();
  const close = vi.fn();
  render(
    <ModalSurface open onClose={close}>
      <p>Scrollable content</p>
    </ModalSurface>,
  );
  const drag = (el: Element) => {
    fireEvent.touchStart(el, { touches: [{ clientY: 10 }] });
    fireEvent.touchMove(el, { touches: [{ clientY: 150 }] });
    fireEvent.touchEnd(el);
    vi.runAllTimers();
  };
  drag(screen.getByText("Scrollable content"));
  expect(close).not.toHaveBeenCalled();
  drag(document.querySelector("[data-modal-handle]")!);
  expect(close).toHaveBeenCalledOnce();
});
test("body stays locked when an underlying modal closes before the top modal", () => {
  const { rerender, unmount } = render(
    <>
      <ModalSurface open onClose={() => {}}>
        First
      </ModalSurface>
      <ModalSurface open onClose={() => {}}>
        Second
      </ModalSurface>
    </>,
  );
  rerender(
    <>
      <ModalSurface open={false} onClose={() => {}}>
        First
      </ModalSurface>
      <ModalSurface open onClose={() => {}}>
        Second
      </ModalSurface>
    </>,
  );
  expect(document.body.style.overflow).toBe("hidden");
  unmount();
  expect(document.body.style.overflow).toBe("");
});

test("image preview receives Escape without dismissing the underlying modal", async () => {
  const { ImageViewer } = await import("../ImageViewer");
  const detailClose = vi.fn();
  const imageClose = vi.fn();
  render(
    <>
      <ModalSurface open onClose={detailClose}>
        <h2>Details</h2>
      </ModalSurface>
      <ImageViewer src="/preview.png" isOpen onClose={imageClose} />
    </>,
  );
  fireEvent.keyDown(document, { key: "Escape" });
  expect(imageClose).toHaveBeenCalledOnce();
  expect(detailClose).not.toHaveBeenCalled();
});
