import { readFileSync } from "node:fs";
function source(path: string) {
  return readFileSync(new URL(path, import.meta.url), "utf8");
}

function cssBlock(sourceText: string, selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = sourceText.match(new RegExp(`${escaped}\\s*\\{([^}]*)\\}`));
  expect(match).toBeTruthy();
  return match[1];
}

const componentsCss = source("../../../styles/components.css");

test("panel search inputs use an editing-safe shared input", () => {
  const panelHeader = source("../PanelHeader.tsx");
  const searchInput = source("../PanelSearchInput.tsx");

  expect(panelHeader).toMatch(/import \{ PanelSearchInput \}/);
  expect(panelHeader).toMatch(/<PanelSearchInput/);
  expect(searchInput).toMatch(/isEditingRef/);
  expect(searchInput).toMatch(/onCompositionStart/);
  expect(searchInput).toMatch(/onCompositionEnd/);
  expect(searchInput).toMatch(/if \(!isEditingRef\.current\)/);
});

test("panel headers use static mobile density instead of scroll compression", () => {
  const panelHeader = source("../PanelHeader.tsx");

  expect(panelHeader).not.toMatch(/PANEL_HEADER_COMPACT_SCROLL_TOP/);
  expect(panelHeader).not.toMatch(/const \[isCompact, setIsCompact\]/);
  expect(panelHeader).not.toMatch(/detectScrollRoot/);
  expect(panelHeader).not.toMatch(/addEventListener\("scroll"/);
  expect(panelHeader).not.toMatch(/panel-header--compact/);
  expect(componentsCss).not.toMatch(/\.panel-header\.panel-header--compact/);
  expect(componentsCss).toMatch(
    /@media \(max-width:\s*639px\) \{[\s\S]*?\.panel-header\s*\{[\s\S]*?padding:\s*0\.5rem 1rem 0\.625rem;/,
  );
  expect(componentsCss).toMatch(
    /@media \(max-width:\s*639px\) \{[\s\S]*?\.panel-header \.panel-header__icon\s*\{[\s\S]*?display:\s*none;/,
  );
  expect(componentsCss).toMatch(
    /@media \(max-width:\s*639px\) \{[\s\S]*?\.panel-header \.panel-header__subtitle\s*\{[\s\S]*?display:\s*none;/,
  );
  expect(panelHeader).toMatch(/panel-header--has-search/);
  expect(componentsCss).toMatch(
    /@media \(max-width:\s*639px\) \{[\s\S]*?\.panel-header\.panel-header--has-search \.panel-header__top\s*\{[\s\S]*?display:\s*none;/,
  );
});

test("panel headers move mobile actions into a search-row overflow menu", () => {
  const panelHeader = source("../PanelHeader.tsx");

  expect(panelHeader).toMatch(/MoreHorizontal/);
  expect(panelHeader).toMatch(/<MoreHorizontal size=\{22\}/);
  expect(panelHeader).toMatch(/flattenActionNodes/);
  expect(panelHeader).toMatch(/panel-header__search-box/);
  expect(panelHeader).toMatch(/panel-header__desktop-actions/);
  expect(panelHeader).toMatch(/panel-header__mobile-actions/);
  expect(panelHeader).toMatch(/panel-header__mobile-actions--search/);
  expect(panelHeader).toMatch(/panel-header__mobile-more--inline/);
  expect(panelHeader).toMatch(/panel-header__mobile-menu/);
  expect(panelHeader).toMatch(/closest\("\[data-panel-header-dropdown\]"\)/);
  expect(panelHeader).toMatch(/panel-header__search-accessory/);
  expect(panelHeader).toMatch(/searchActions/);
  expect(panelHeader).toMatch(/panel-header__search-actions/);
  expect(panelHeader).toMatch(/panel-header--search-only/);
  expect(panelHeader).toMatch(/panel-header__mobile-menu-accessory/);
  expect(panelHeader).not.toMatch(/panel-header__mobile-primary/);
  expect(componentsCss).toMatch(/\.panel-header__desktop-actions/);
  expect(componentsCss).toMatch(/\.panel-header__mobile-actions/);
  expect(componentsCss).toMatch(/\.panel-header__search-accessory/);
  expect(componentsCss).toMatch(/\.panel-header__mobile-menu-accessory/);
  expect(componentsCss).toMatch(
    /\.panel-header__actions > :is\(button, a, select\),[\s\S]*?\.panel-header__search-actions > \.flex > :is\(button, a, select\)\s*\{[\s\S]*?height:\s*2\.5rem;[\s\S]*?min-height:\s*2\.5rem;/,
  );
  expect(componentsCss).toMatch(
    /\.panel-header__mobile-menu-accessory\s*>\s*:is\(\.relative, \.flex, \.panel-header-actions\),\s*\.panel-header__mobile-menu-item\s*>\s*:is\(\.relative, \.flex, \.panel-header-actions\)\s*\{[\s\S]*?display:\s*grid;[\s\S]*?width:\s*100%;[\s\S]*?gap:\s*0\.375rem;/,
  );
  const mobileMenuBlock = cssBlock(componentsCss, ".panel-header__mobile-menu");
  expect(mobileMenuBlock).toMatch(
    /width:\s*min\(18rem,\s*calc\(100vw - 2rem\)\);/,
  );
  expect(mobileMenuBlock).toMatch(/min-width:\s*0;/);
  expect(componentsCss).toMatch(/\.panel-header__mobile-more > svg/);
  expect(componentsCss).toMatch(
    /\.panel-header__mobile-more > svg\s*\{[\s\S]*?width:\s*1\.25rem;[\s\S]*?height:\s*1\.25rem;/,
  );
  expect(componentsCss).toMatch(
    /\.panel-header__mobile-more--inline > svg\s*\{[\s\S]*?width:\s*1\.375rem;[\s\S]*?height:\s*1\.375rem;/,
  );
  expect(componentsCss).toMatch(
    /\.panel-header__mobile-menu :is\(\.hidden, \.sm\\:inline\)\s*\{[\s\S]*?display:\s*inline-flex !important;/,
  );
  expect(componentsCss).toMatch(
    /\.panel-header__mobile-menu-item > :is\(button, a\),[\s\S]*?\.panel-header__mobile-menu-accessory \[data-filter-menu\] > button\s*\{[\s\S]*?display:\s*flex;[\s\S]*?width:\s*100%;[\s\S]*?justify-content:\s*flex-start;/,
  );
  expect(componentsCss).toMatch(
    /\.panel-header__mobile-menu-item[\s\S]*?> \.panel-header-actions[\s\S]*?\[data-filter-menu\][\s\S]*?\.panel-filter-trigger,[\s\S]*?\{[\s\S]*?display:\s*flex;[\s\S]*?width:\s*100%;[\s\S]*?justify-content:\s*flex-start;/,
  );
  expect(componentsCss).toMatch(
    /\.panel-header__mobile-menu-item > :is\(button, a\),[\s\S]*?\.panel-header__mobile-menu-accessory \[data-filter-menu\] > button\s*\{[\s\S]*?height:\s*2\.5rem;[\s\S]*?background-color:\s*transparent !important;[\s\S]*?color:\s*var\(--theme-text\) !important;[\s\S]*?box-shadow:\s*none !important;/,
  );
  expect(componentsCss).toMatch(
    /\.panel-header__mobile-menu-item > :is\(button, a\):hover,[\s\S]*?\.panel-header__mobile-menu-accessory \[data-filter-menu\] > button:hover\s*\{[\s\S]*?background-color:\s*color-mix\([\s\S]*?var\(--theme-primary\) 8%,[\s\S]*?transparent[\s\S]*?\) !important;/,
  );
  expect(componentsCss).toMatch(
    /\.panel-header__mobile-menu-item > :is\(button, a\) > :is\(\.hidden, \.sm\\:inline\),[\s\S]*?\.panel-header__mobile-menu-accessory[\s\S]*?\[data-filter-menu\][\s\S]*?> button[\s\S]*?> :is\(\.hidden, \.sm\\:inline\)\s*\{[\s\S]*?flex:\s*1 1 auto;/,
  );
  expect(componentsCss).toMatch(
    /\.panel-header__mobile-menu-item > :is\(button, a\) > svg:last-child,[\s\S]*?\.panel-header__mobile-menu-accessory[\s\S]*?\[data-filter-menu\][\s\S]*?> button[\s\S]*?> svg:last-child\s*\{[\s\S]*?margin-left:\s*auto;/,
  );
  expect(componentsCss).toMatch(
    /\.panel-header__mobile-menu \.skill-filter-dropdown\s*\{[\s\S]*?position:\s*absolute;[\s\S]*?width:\s*100%;[\s\S]*?max-height:\s*min\(46dvh,\s*18rem\);[\s\S]*?overflow-y:\s*auto;/,
  );
  expect(componentsCss).toMatch(
    /@media \(max-width:\s*639px\) \{[\s\S]*?\.panel-header__desktop-actions\s*\{[\s\S]*?display:\s*none;/,
  );
  expect(componentsCss).toMatch(
    /@media \(max-width:\s*639px\) \{[\s\S]*?\.panel-header__mobile-actions\s*\{[\s\S]*?display:\s*flex;/,
  );
  expect(componentsCss).toMatch(
    /@media \(max-width:\s*639px\) \{[\s\S]*?\.panel-header \.panel-header__search-box\s*\{[\s\S]*?position:\s*relative;/,
  );
  expect(componentsCss).toMatch(
    /@media \(max-width:\s*639px\) \{[\s\S]*?\.panel-header__mobile-actions--search\s*\{[\s\S]*?position:\s*absolute;[\s\S]*?inset:\s*0;[\s\S]*?transform:\s*none;/,
  );
  expect(componentsCss).toMatch(
    /@media \(max-width:\s*639px\) \{[\s\S]*?\.panel-header__mobile-actions--search \.panel-header__mobile-more\s*\{[\s\S]*?position:\s*absolute;[\s\S]*?right:\s*0\.125rem;/,
  );
  expect(componentsCss).toMatch(
    /@media \(max-width:\s*639px\) \{[\s\S]*?\.panel-header__mobile-actions--search \.panel-header__mobile-menu\s*\{[\s\S]*?left:\s*0;[\s\S]*?right:\s*0;[\s\S]*?width:\s*100%;[\s\S]*?max-height:\s*min\(70dvh,\s*26rem\);/,
  );
  expect(componentsCss).toMatch(
    /\.panel-header__mobile-more--inline\s*\{[\s\S]*?border:\s*0;[\s\S]*?background:\s*transparent;/,
  );
  expect(componentsCss).toMatch(
    /@media \(max-width:\s*639px\) \{[\s\S]*?\.panel-header \.panel-header__search-accessory\s*\{[\s\S]*?display:\s*none;/,
  );
  expect(panelHeader).not.toMatch(
    /className="btn-secondary panel-header__mobile-more/,
  );
});

test("panel filter dropdowns use viewport-clamped left positioning via useStickyDropdownPosition hook", () => {
  const panelControls = source("../PanelControls.tsx");

  expect(panelControls).toMatch(/useStickyDropdownPosition/);
  expect(panelControls).toMatch(
    /const dropdownStyle = useStickyDropdownPosition/,
  );
  expect(panelControls).toMatch(/const left = Math\.max\(/);
  expect(panelControls).toMatch(/left,/);
  expect(panelControls).not.toMatch(/right:\s*Math\.max/);
  expect(panelControls).toMatch(/window\.visualViewport/);
});

test("panel header mounts search accessory only once while the mobile overflow menu is open", () => {
  const panelHeader = source("../PanelHeader.tsx");

  expect(panelHeader).toMatch(/\{searchAccessory && !isMobileMenuOpen && \(/);
});

test("panel header dropdown portals are viewport-aware and do not collapse the parent mobile menu", () => {
  const scopeDropdown = source("../../persona/PersonaScopeDropdown.tsx");
  const tagDropdown = source("../../persona/PersonaTagFilterDropdown.tsx");
  const teamPanel = source("../../team/TeamBuilderWrapper.tsx");
  const personaPanel = source("../../persona/PersonaPlazaPanel.tsx");

  for (const file of [scopeDropdown, tagDropdown]) {
    expect(file).toMatch(/data-panel-header-dropdown/);
    expect(file).toMatch(/getDropdownPosition/);
    expect(file).toMatch(/DROPDOWN_GUTTER/);
    expect(file).toMatch(/window\.innerWidth/);
    expect(file).toMatch(/onPointerDown=\{onClose\}/);
    expect(file).toMatch(/onPointerDown=\{\(e\) => e\.stopPropagation\(\)\}/);
    expect(file).toMatch(/event\.key === "Escape"/);
    expect(file).toMatch(/role="menu"/);
  }

  expect(scopeDropdown).toMatch(/role="menuitemradio"/);
  expect(scopeDropdown).toMatch(/aria-checked=\{scopeFilter === key\}/);
  expect(tagDropdown).toMatch(/aria-pressed=\{activeTag === tag\}/);

  for (const file of [teamPanel, personaPanel]) {
    expect(file).toMatch(/aria-haspopup="menu"/);
    expect(file).toMatch(/aria-expanded=\{isScopeOpen\}/);
    expect(file).toMatch(/aria-expanded=\{isFilterOpen\}/);
  }
});

test("marketplace refresh action has a mobile menu label", () => {
  const marketplacePanel = source("../../panels/MarketplacePanel.tsx");

  expect(marketplacePanel).toMatch(
    /<RotateCw size=\{16\} \/>\s*<span className="hidden sm:inline">\s*\{t\("common\.refresh"\)\}\s*<\/span>/,
  );
});

test("notification panel header aligns with shared panel spacing", () => {
  const notificationPanel = source("../../panels/NotificationPanel.tsx");

  expect(notificationPanel).toMatch(/<PanelHeader/);
  expect(notificationPanel).toMatch(/<Button[\s\S]*?variant="primary"/);
  expect(notificationPanel).toMatch(/leftIcon=\{<Plus size=\{16\} \/>\}/);
  expect(notificationPanel).not.toMatch(
    /inline-flex items-center gap-2 rounded-xl bg-stone-900 px-4 py-2\.5/,
  );
  expect(notificationPanel).toMatch(
    /className="flex-1 overflow-y-auto px-4 py-2 sm:p-6 lg:px-8"/,
  );
  expect(notificationPanel).toMatch(
    /className="glass-divider bg-transparent px-4 py-4 sm:px-6 lg:px-8"/,
  );
});

test("direct panel-search fields opt into the same refresh-safe behavior", () => {
  for (const path of [
    "../../panels/SettingsPanel.tsx",
    "../../team/RoleSquare.tsx",
  ]) {
    const file = source(path);
    expect(file).toMatch(/PanelSearchInput/);
    expect(file).not.toMatch(/<input[^>]*className="panel-search/);
  }

  for (const path of [
    "../../panels/MarketplacePanel.tsx",
    "../../panels/SkillsPanel/SkillsList.tsx",
  ]) {
    const file = source(path);
    expect(file).toMatch(/PanelHeader/);
    expect(file).not.toMatch(/<input[^>]*className="panel-search/);
  }
});

test("selector search fields share editing-safe input behavior", () => {
  for (const path of [
    "../../mcp/RoleSelector.tsx",
    "../../mcp/EnvKeysSelector.tsx",
    "../../agent/ModelSelector.tsx",
    "../../team/TeamBuilder.tsx",
    "../../team/TeamPickerModal.tsx",
    "../../persona/PersonaEditorSkillSelector.tsx",
    "../../persona/PersonaPresetSelector.tsx",
    "../../panels/SearchDialog.tsx",
    "../../panels/channel/ChannelPersonaSelect.tsx",
    "../../fileLibrary/components/Toolbar.tsx",
    "../../panels/ModelPanel/tabs/ModelIconSelect.tsx",
    "../../panels/AgentPanel/shared/ProviderSelect.tsx",
  ]) {
    const file = source(path);
    expect(file).toMatch(/PanelSearchInput/);
    expect(file).not.toMatch(
      /onChange=\{\((?:e|event)\) => (?:set[A-Za-z0-9_]*Search|setSearchQuery|setQuery|onSearchChange)\((?:e|event)\.target\.value\)\}/,
    );
  }
});

test("search panels keep their header mounted while a search refresh is loading", () => {
  for (const path of [
    "../../persona/PersonaPlazaPanel.tsx",
    "../../panels/MarketplacePanel.tsx",
    "../../panels/SkillsPanel/SkillsList.tsx",
    "../../panels/MCPPanel.tsx",
    "../../panels/RolesPanel.tsx",
    "../../panels/UsersPanel.tsx",
  ]) {
    const file = source(path);
    expect(file).not.toMatch(/if \(isLoading\)\s*\{\s*return <[^>]+Skeleton/);
    expect(file).toMatch(/isInitialLoading/);
  }
});
