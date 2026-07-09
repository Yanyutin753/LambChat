import { readFileSync } from "node:fs";
const skillCss = readFileSync(new URL("../skill.css", import.meta.url), "utf8");

function cssRuleBody(selector: string): string {
  const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = skillCss.match(
    new RegExp(`${escapedSelector}\\s*\\{([^}]*)\\}`),
  );
  expect(match).toBeTruthy();
  return match[1];
}

test("skills hub tabs align with panels without adding a colored switch background", () => {
  const tabsRule = cssRuleBody(".skills-hub-tabs");
  const groupRule = cssRuleBody(".skills-hub-tabs__group");
  const itemRule = cssRuleBody(".skills-hub-tabs__item");
  const activeRule = cssRuleBody(".skills-hub-tabs__item--active");

  expect(skillCss).toMatch(
    /\.skills-hub-tabs\s*\{[\s\S]*?align-items:\s*center;[\s\S]*?padding:\s*0\.625rem 1rem 0\.5rem;/,
  );
  expect(tabsRule).not.toMatch(/background:/);
  expect(skillCss).toMatch(
    /\.skills-hub-tabs__group\s*\{[\s\S]*?display:\s*inline-flex;[\s\S]*?width:\s*auto;[\s\S]*?padding:\s*0;/,
  );
  expect(groupRule).not.toMatch(/background:/);
  expect(skillCss).toMatch(
    /\.skills-hub-tabs__item\s*\{[\s\S]*?flex:\s*0 0 auto;[\s\S]*?min-height:\s*2rem;/,
  );
  expect(itemRule).not.toMatch(/background:/);
  expect(activeRule).not.toMatch(/background:/);
  expect(skillCss).toMatch(
    /\.skills-hub-tabs__item--active::after\s*\{[\s\S]*?background:\s*var\(--theme-primary\);/,
  );
  expect(skillCss).toMatch(
    /@media \(max-width:\s*639px\) \{[\s\S]*?\.skills-hub-tabs\s*\{[\s\S]*?padding:\s*0\.5rem 0\.75rem 0\.375rem;/,
  );
  expect(skillCss).toMatch(
    /@media \(max-width:\s*639px\) \{[\s\S]*?\.skills-hub-tabs__group\s*\{[\s\S]*?width:\s*100%;/,
  );
  expect(skillCss).toMatch(
    /@media \(min-width:\s*640px\) \{[\s\S]*?\.skills-hub-tabs\s*\{[\s\S]*?padding:\s*0\.875rem 1\.5rem 0\.625rem;/,
  );
  expect(skillCss).toMatch(
    /@media \(min-width:\s*1024px\) \{[\s\S]*?\.skills-hub-tabs\s*\{[\s\S]*?padding:\s*1rem 2rem 0\.75rem;/,
  );
});
