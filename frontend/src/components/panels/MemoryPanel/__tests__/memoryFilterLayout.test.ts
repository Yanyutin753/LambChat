import { readFileSync } from "node:fs";
const filterSource = readFileSync(
  new URL("../MemoryFilter.tsx", import.meta.url),
  "utf8",
);
const componentsCss = readFileSync(
  new URL("../../../../styles/components.css", import.meta.url),
  "utf8",
);
const skillsListSource = readFileSync(
  new URL("../../SkillsPanel/SkillsList.tsx", import.meta.url),
  "utf8",
);
const marketplaceSource = readFileSync(
  new URL("../../MarketplacePanel.tsx", import.meta.url),
  "utf8",
);
const skillFilterDropdownSource = readFileSync(
  new URL("../../SkillFilterDropdown.tsx", import.meta.url),
  "utf8",
);
const panelControlsSource = readFileSync(
  new URL("../../../common/PanelControls.tsx", import.meta.url),
  "utf8",
);

test("memory filter trigger uses shared stable panel filter sizing", () => {
  expect(filterSource).toMatch(/data-filter-menu/);
  expect(filterSource).not.toMatch(/className="panel-search[^"]*h-10/);
  expect(filterSource).toMatch(/import \{ PanelFilterSelect \}/);
  expect(filterSource).toMatch(
    /<PanelFilterSelect[\s\S]*onChange=\{typeOnChange\}/,
  );
  expect(filterSource).toMatch(
    /<PanelFilterSelect[\s\S]*onChange=\{sourceOnChange\}/,
  );
  expect(filterSource).toMatch(/panel-filter-trigger/);
  expect(filterSource).toMatch(/panel-filter-trigger__label/);
  expect(filterSource).not.toMatch(/<Button[\s\S]*panel-filter-trigger/);
  expect(filterSource).not.toMatch(/import \{ Select \}/);

  expect(componentsCss).toMatch(
    /\.panel-filter-select\s*\{[\s\S]*?min-width:\s*min\(10rem,\s*42vw\);[\s\S]*?max-width:\s*min\(13rem,\s*42vw\);/,
  );
  expect(componentsCss).toMatch(
    /\.panel-filter-trigger\s*\{[\s\S]*?max-width:\s*100%;[\s\S]*?justify-content:\s*space-between;/,
  );
  expect(componentsCss).toMatch(
    /\.panel-filter-trigger__label\s*\{[\s\S]*?flex:\s*1 1 auto;[\s\S]*?overflow:\s*hidden;[\s\S]*?text-overflow:\s*ellipsis;/,
  );
  expect(componentsCss).toMatch(
    /\.panel-filter-trigger \.ui-button__label\s*\{[\s\S]*?display:\s*flex;[\s\S]*?width:\s*100%;/,
  );
  expect(componentsCss).toMatch(
    /\.panel-filter-trigger \.ui-button__label > svg:last-child\s*\{[\s\S]*?margin-left:\s*auto;/,
  );
  expect(componentsCss).toMatch(
    /\.ui-select-dropdown,\s*[\s\S]*?\.glass-select-dropdown\s*\{[\s\S]*?max-height:\s*14rem;[\s\S]*?overflow-y:\s*auto;/,
  );
  expect(componentsCss).toMatch(
    /\.panel-header__mobile-menu-accessory \[data-filter-menu\] \.panel-filter-trigger\s*\{[\s\S]*?max-width:\s*none;/,
  );
});

test("tag filter dropdowns opt into stable mobile filter-menu behavior", () => {
  expect(panelControlsSource).toMatch(/data-filter-menu/);
  expect(panelControlsSource).toMatch(/panel-filter-menu/);
  expect(skillsListSource).toMatch(/SkillFilterDropdown/);
  expect(skillsListSource).not.toMatch(/<FilterDropdown/);
  expect(marketplaceSource).toMatch(/SkillFilterDropdown/);
  expect(marketplaceSource).not.toMatch(/<FilterDropdown/);
  expect(skillFilterDropdownSource).toMatch(/data-panel-header-dropdown/);
  expect(skillFilterDropdownSource).toMatch(
    /className="fixed inset-0 z-\[999\]"/,
  );
  expect(skillFilterDropdownSource).toMatch(
    /skill-filter-dropdown panel-header-dropdown/,
  );
  expect(skillFilterDropdownSource).toMatch(/role="menu"/);
  expect(skillFilterDropdownSource).toMatch(/getDropdownPosition/);
  expect(skillFilterDropdownSource).toMatch(/window\.visualViewport/);
  expect(skillFilterDropdownSource).toMatch(/skill-filter-segment/);
  expect(skillFilterDropdownSource).toMatch(/skill-tag-chip/);
  expect(skillFilterDropdownSource).toMatch(/aria-haspopup="menu"/);
  expect(skillFilterDropdownSource).toMatch(/aria-expanded=\{isOpen\}/);
  expect(skillFilterDropdownSource).toMatch(
    /aria-pressed=\{selectedTags\.includes\(tag\)\}/,
  );
});
