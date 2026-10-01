import { readFileSync } from "node:fs";

const skillCss = readFileSync(new URL("../skill.css", import.meta.url), "utf8");
const hubSource = readFileSync(
  new URL("../../components/panels/SkillsHubPanel.tsx", import.meta.url),
  "utf8",
);

test("skills hub switch stays in the header action area on narrow and wide panels", () => {
  expect(hubSource).toMatch(
    /actions=\{[\s\S]*?showTabSwitcher[\s\S]*?skills-hub-tabs/,
  );
  expect(hubSource).toContain('className="panel-header--section-switch"');
  expect(skillCss).toMatch(
    /\.panel-header--section-switch \.panel-header__top\s*\{[^}]*flex-wrap:\s*nowrap;/,
  );
  expect(skillCss).toMatch(
    /\.panel-header--section-switch \.panel-header__identity\s*\{[^}]*flex:\s*1 1 0;/,
  );
  expect(skillCss).toMatch(/\.skills-hub-tabs\s*\{[^}]*padding:\s*0;/);
  expect(skillCss).toMatch(
    /\.skills-hub-tabs__item\s*\{[^}]*min-height:\s*2\.75rem;/,
  );
  expect(skillCss).toMatch(
    /@container panel \(max-width: 639px\)[\s\S]*?\.panel-header--section-switch \.panel-header__desktop-actions\s*\{[^}]*display:\s*flex;/,
  );
  expect(skillCss).toMatch(
    /\.panel-header--section-switch \.panel-header__subtitle,[\s\S]*?display:\s*none;/,
  );
});

test("agent and model switch gives long compact titles their own row", () => {
  const source = readFileSync(
    new URL(
      "../../components/panels/AgentModelPanel/AgentModelPanel.tsx",
      import.meta.url,
    ),
    "utf8",
  );
  expect(source).toMatch(
    /className="panel-header--section-switch panel-header--agent-model"/,
  );
  expect(skillCss).toMatch(
    /@container panel \(max-width: 639px\)[\s\S]*?\.panel-header--agent-model \.panel-header__top\s*\{[^}]*flex-wrap:\s*wrap;/,
  );
  expect(skillCss).toMatch(
    /\.panel-header--agent-model \.panel-header__identity\s*\{[^}]*flex:\s*1 1 100%;/,
  );
  expect(skillCss).toMatch(
    /\.panel-header--agent-model \.panel-header__title\s*\{[^}]*white-space:\s*normal;/,
  );
});

test("inline switches do not receive the page inset twice", () => {
  const panelsCss = readFileSync(
    new URL("../panels.css", import.meta.url),
    "utf8",
  );
  expect(panelsCss).not.toContain(".skills-hub-tabs");
});

test("skills hub header and search share the list spacing without stacked padding", () => {
  const panelsCss = readFileSync(
    new URL("../panels.css", import.meta.url),
    "utf8",
  );
  expect(panelsCss).toMatch(
    /\.skill-theme-shell > \.panel-header--section-switch\s*\{[^}]*padding-bottom:\s*0;/,
  );
  expect(panelsCss).toMatch(
    /\.skill-theme-shell \.panel-header--search-only\s*\{[^}]*padding-block:\s*var\(--panel-gap\) 0;/,
  );
});
