import { existsSync } from "node:fs";
import { expect, test } from "vitest";
import {
  MAIN_SHOTS,
  MGMT_SHOTS,
  RESPONSIVE_SHOTS,
  themedShots,
  shotSrc,
} from "../data";

const shots = [...MAIN_SHOTS, ...MGMT_SHOTS, ...RESPONSIVE_SHOTS];

test("light screenshots keep their existing URLs", () => {
  expect(themedShots(shots, "light")).toEqual(shots);
});

test.each(["dark", "sepia"] as const)(
  "%s screenshots preserve labels and cache versions",
  (theme) => {
    const themed = themedShots(shots, theme);
    expect(themed).toHaveLength(8);
    themed.forEach((shot, index) => {
      expect(shot.altKey).toBe(shots[index].altKey);
      expect(shot.src).toBe(
        shots[index].src.replace(".webp?", `-${theme}.webp?`),
      );
    });
    expect(shots[0].src).not.toContain(`-${theme}.webp`);
  },
);

test.each(["light", "dark", "sepia"] as const)(
  "all %s screenshot assets exist",
  (theme) => {
    for (const shot of themedShots(shots, theme)) {
      const asset = new URL(
        `../../../../public${shot.src.split("?")[0]}`,
        import.meta.url,
      );
      expect(existsSync(asset), shot.src).toBe(true);
    }
  },
);

test.each(["light", "dark", "sepia"] as const)(
  "architecture uses the matching %s asset",
  (theme) => {
    const src = shotSrc("architecture", theme);
    const suffix = theme === "light" ? "" : `-${theme}`;
    expect(src).toContain(`/architecture${suffix}.webp?`);
    expect(
      existsSync(
        new URL(`../../../../public${src.split("?")[0]}`, import.meta.url),
      ),
    ).toBe(true);
  },
);
