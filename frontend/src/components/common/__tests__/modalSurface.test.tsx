/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
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

test("background stays inert until every modal and image preview closes", async () => {
  const { ImageViewer } = await import("../ImageViewer");
  const view = (details: boolean, image: boolean) => (
    <div id="root">
      <button>Background</button>
      <ModalSurface open={details} onClose={() => {}}>
        Details
      </ModalSurface>
      <ImageViewer isOpen={image} src="/preview.png" onClose={() => {}} />
    </div>
  );
  const expandedHost = document.createElement("div");
  expandedHost.dataset.chatComposerHost = "";
  document.body.append(expandedHost);
  const { rerender, unmount } = render(view(true, true));
  const root = document.getElementById("root")!;
  expect(root.inert).toBe(true);
  expect(expandedHost.inert).toBe(true);
  rerender(view(false, true));
  expect(root.inert).toBe(true);
  expect(expandedHost.inert).toBe(true);
  rerender(view(false, false));
  expect(root.inert).toBe(false);
  expect(expandedHost.inert).toBe(false);
  expandedHost.remove();
  unmount();
});

test.each(["modal", "image"])(
  "%s keeps its original opener across option changes",
  async (kind) => {
    const { ImageViewer } = await import("../ImageViewer");
    const view = (open: boolean, changed = false) => (
      <div id="root">
        <button>Opener</button>
        {kind === "modal" ? (
          <ModalSurface
            open={open}
            dismissible={!changed}
            onClose={() => {}}
            label="Details"
          >
            <input aria-label="Details" />
          </ModalSurface>
        ) : (
          <ImageViewer
            isOpen={open}
            src={changed ? "/second.png" : "/first.png"}
            hasNext={!changed}
            onNext={() => {}}
            onClose={() => {}}
          />
        )}
      </div>
    );
    const { rerender } = render(view(false));
    const opener = screen.getByRole("button", { name: "Opener" });
    opener.focus();
    rerender(view(true));
    await act(async () => rerender(view(true, true)));
    expect(screen.getByRole("dialog").contains(document.activeElement)).toBe(
      true,
    );
    await act(async () => rerender(view(false, true)));
    expect(opener).toHaveFocus();
  },
);
