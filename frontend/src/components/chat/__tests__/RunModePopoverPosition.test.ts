import { getRunModePopoverPosition } from "../runModePopoverPosition";

function rect(overrides: Partial<DOMRect>): DOMRect {
  return {
    x: overrides.left ?? 0,
    y: overrides.top ?? 0,
    left: 0,
    top: 0,
    right: 0,
    bottom: 0,
    width: 0,
    height: 0,
    toJSON: () => ({}),
    ...overrides,
  } as DOMRect;
}

test("run mode popover fits within a short mobile viewport", () => {
  const style = getRunModePopoverPosition({
    triggerRect: rect({ left: 96, top: 96, width: 44, height: 36 }),
    viewportWidth: 360,
    viewportHeight: 560,
  });

  expect(style).toMatchObject({
    position: "fixed",
    zIndex: 9999,
    width: 280,
    left: 40,
    top: 16,
    maxHeight: 528,
  });
  expect(style).not.toHaveProperty("bottom");
});

test("run mode popover keeps desktop placement above the trigger", () => {
  const style = getRunModePopoverPosition({
    triggerRect: rect({ left: 400, top: 640, width: 48, height: 36 }),
    viewportWidth: 1280,
    viewportHeight: 800,
  });

  expect(style).toMatchObject({
    position: "fixed",
    zIndex: 9999,
    width: 320,
    left: 264,
    bottom: 168,
    maxHeight: 616,
  });
  expect(style).not.toHaveProperty("top");
});
