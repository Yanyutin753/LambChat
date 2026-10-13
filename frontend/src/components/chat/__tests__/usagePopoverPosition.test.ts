import { expect, test } from "vitest";
import { getUsagePopoverPosition } from "../usagePopoverPosition";

test.each([
  { width: 1440, height: 900, right: 1370, expectedLeft: 1120, expectedWidth: 304 },
  { width: 320, height: 568, right: 272, expectedLeft: 16, expectedWidth: 288 },
])("header usage card opens below the trigger within a $width px viewport", ({ width, height, right, expectedLeft, expectedWidth }) => {
  const position = getUsagePopoverPosition({
    triggerRect: { left: right - 36, right, top: 12, bottom: 48, width: 36 } as DOMRect,
    viewportWidth: width,
    viewportHeight: height,
  });
  expect(position).toMatchObject({
    top: 56,
    left: expectedLeft,
    width: expectedWidth,
    maxHeight: height - 72,
  });
  expect(position.bottom).toBeUndefined();
});
