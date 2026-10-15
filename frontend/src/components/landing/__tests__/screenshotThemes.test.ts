import { expect, test } from "vitest";
import { MAIN_SHOTS, MGMT_SHOTS, RESPONSIVE_SHOTS, themedShots } from "../data";

const shots = [...MAIN_SHOTS, ...MGMT_SHOTS, ...RESPONSIVE_SHOTS];

test("light screenshots keep their existing URLs", () => {
  expect(themedShots(shots, "light")).toEqual(shots);
});

test.each(["dark", "sepia"] as const)("%s screenshots preserve labels and cache versions", (theme) => {
  const themed = themedShots(shots, theme);
  expect(themed).toHaveLength(8);
  themed.forEach((shot, index) => {
    expect(shot.altKey).toBe(shots[index].altKey);
    expect(shot.src).toBe(shots[index].src.replace(".webp?", `-${theme}.webp?`));
  });
  expect(shots[0].src).not.toContain(`-${theme}.webp`);
});
