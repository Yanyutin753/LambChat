import { readFileSync } from "node:fs";
import { join } from "node:path";

const componentSource = readFileSync(
  join(import.meta.dirname, "../SkillCard.tsx"),
  "utf8",
);

test("skill cards expose pin and favorite banner actions", () => {
  expect(componentSource).toMatch(/Pin,/);
  expect(componentSource).toMatch(/Star,/);
  expect(componentSource).toMatch(/onTogglePreference\?:/);
  expect(componentSource).toMatch(/pps-card__icon-action--active-pin/);
  expect(componentSource).toMatch(/pps-card__icon-action--active-fav/);
  expect(componentSource).toMatch(/t\("personaPresets\.pin", "置顶"\)/);
  expect(componentSource).toMatch(/t\("personaPresets\.favorite", "收藏"\)/);
});
