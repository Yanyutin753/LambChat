import { describe, expect, test } from "vitest";
import { getAnchoredSlashDropdownPlacement } from "../slashDropdownPlacement";

function rect(left: number, top: number, bottom: number): DOMRect {
  return { left, top, bottom } as DOMRect;
}

describe("getAnchoredSlashDropdownPlacement", () => {
  test("opens below the caret when the full menu fits", () => {
    expect(
      getAnchoredSlashDropdownPlacement(rect(120, 100, 120), 1000, 700),
    ).toMatchObject({ top: 126, maxHeight: 320 });
  });

  test("flips above the caret when only the upper side fits", () => {
    expect(
      getAnchoredSlashDropdownPlacement(rect(120, 560, 580), 1000, 700),
    ).toMatchObject({ bottom: 146, maxHeight: 320 });
  });

  test("uses a viewport-height sheet when neither side can fit", () => {
    expect(
      getAnchoredSlashDropdownPlacement(rect(120, 90, 110), 1000, 260),
    ).toMatchObject({ top: 8, maxHeight: 244 });
  });

  test("keeps the mobile popup compact", () => {
    expect(
      getAnchoredSlashDropdownPlacement(
        rect(24, 500, 520),
        390,
        844,
        240,
        288,
        12,
      ),
    ).toMatchObject({ width: 288, maxHeight: 240 });
  });
});
