/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ResourceCardMenu } from "../ResourceCardMenu";
import type { ResourceCardAction } from "../ResourceCardMenu";

afterEach(cleanup);

const actions: ResourceCardAction[] = [
  { label: "Action", onClick: vi.fn() },
];

type AnchorRef = React.RefObject<HTMLButtonElement | null>;

function rect(top: number) {
  return {
    top,
    left: 0,
    right: 16,
    bottom: top + 16,
    width: 16,
    height: 16,
    x: 0,
    y: top,
    toJSON: () => ({}),
  } as DOMRect;
}

// 先挂锚点、打好 rect 桩，再挂菜单——保证菜单挂载时捕获到的是桩矩形
function mountAnchorWithRect(top: number): {
  anchorRef: AnchorRef;
  setRect: (top: number) => void;
  unmountAnchor: () => void;
} {
  const anchorRef: AnchorRef = { current: null };
  const anchorRender = render(
    <button ref={anchorRef} type="button" data-testid="menu-anchor" />,
  );
  const anchor = screen.getByTestId("menu-anchor");
  anchor.getBoundingClientRect = () => rect(top);
  let currentTop = top;
  return {
    anchorRef,
    setRect: (next) => {
      currentTop = next;
      anchor.getBoundingClientRect = () => rect(currentTop);
    },
    unmountAnchor: () => anchorRender.unmount(),
  };
}

function renderMenu(onClose: () => void, anchorRef?: AnchorRef) {
  render(
    <div data-testid="unrelated-scroller">
      <ResourceCardMenu
        id="menu-1"
        title="Menu"
        actions={actions}
        position={{ x: 8, y: 8 }}
        onClose={onClose}
        anchorRef={anchorRef}
      />
    </div>,
  );
}

function scrollUnrelatedScroller() {
  screen
    .getByTestId("unrelated-scroller")
    .dispatchEvent(new Event("scroll", { bubbles: false }));
}

test("unrelated scroller scroll keeps the menu open while its anchor stays put", () => {
  const onClose = vi.fn();
  const { anchorRef } = mountAnchorWithRect(100);
  renderMenu(onClose, anchorRef);

  scrollUnrelatedScroller();
  scrollUnrelatedScroller();

  expect(onClose).not.toHaveBeenCalled();
  expect(screen.getByRole("menu", { name: "Menu" })).toBeTruthy();
});

test("scroll closes the menu once its anchor moved", () => {
  const onClose = vi.fn();
  const { anchorRef, setRect } = mountAnchorWithRect(100);
  renderMenu(onClose, anchorRef);
  scrollUnrelatedScroller();
  expect(onClose).not.toHaveBeenCalled();

  setRect(160);
  scrollUnrelatedScroller();

  expect(onClose).toHaveBeenCalledTimes(1);
});

test("scroll closes the menu when its anchor left the document", () => {
  const onClose = vi.fn();
  const { anchorRef, unmountAnchor } = mountAnchorWithRect(100);
  renderMenu(onClose, anchorRef);
  scrollUnrelatedScroller();
  expect(onClose).not.toHaveBeenCalled();

  unmountAnchor();
  scrollUnrelatedScroller();

  expect(onClose).toHaveBeenCalledTimes(1);
});

test("without an anchor, unrelated scroll still closes the menu", () => {
  const onClose = vi.fn();
  renderMenu(onClose);

  scrollUnrelatedScroller();

  expect(onClose).toHaveBeenCalledTimes(1);
});
