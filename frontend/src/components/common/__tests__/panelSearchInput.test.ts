import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

function source(path: string) {
  return readFileSync(new URL(path, import.meta.url), "utf8");
}

function cssBlock(sourceText: string, selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = sourceText.match(new RegExp(`${escaped}\\s*\\{([^}]*)\\}`));
  assert.ok(match, `Expected CSS block for ${selector}`);
  return match[1];
}

const componentsCss = source("../../../styles/components.css");

test("panel search inputs use an editing-safe shared input", () => {
  const panelHeader = source("../PanelHeader.tsx");
  const searchInput = source("../PanelSearchInput.tsx");

  assert.match(panelHeader, /import \{ PanelSearchInput \}/);
  assert.match(panelHeader, /<PanelSearchInput/);
  assert.match(searchInput, /isEditingRef/);
  assert.match(searchInput, /onCompositionStart/);
  assert.match(searchInput, /onCompositionEnd/);
  assert.match(searchInput, /if \(!isEditingRef\.current\)/);
});

test("panel headers use static mobile density instead of scroll compression", () => {
  const panelHeader = source("../PanelHeader.tsx");

  assert.doesNotMatch(panelHeader, /PANEL_HEADER_COMPACT_SCROLL_TOP/);
  assert.doesNotMatch(panelHeader, /const \[isCompact, setIsCompact\]/);
  assert.doesNotMatch(panelHeader, /detectScrollRoot/);
  assert.doesNotMatch(panelHeader, /addEventListener\("scroll"/);
  assert.doesNotMatch(panelHeader, /panel-header--compact/);
  assert.doesNotMatch(componentsCss, /\.panel-header\.panel-header--compact/);
  assert.match(
    componentsCss,
    /@media \(max-width:\s*639px\) \{[\s\S]*?\.panel-header\s*\{[\s\S]*?padding:\s*0\.5rem 1rem 0\.625rem;/,
  );
  assert.match(
    componentsCss,
    /@media \(max-width:\s*639px\) \{[\s\S]*?\.panel-header \.panel-header__icon\s*\{[\s\S]*?display:\s*none;/,
  );
  assert.match(
    componentsCss,
    /@media \(max-width:\s*639px\) \{[\s\S]*?\.panel-header \.panel-header__subtitle\s*\{[\s\S]*?display:\s*none;/,
  );
  assert.match(panelHeader, /panel-header--has-search/);
  assert.match(
    componentsCss,
    /@media \(max-width:\s*639px\) \{[\s\S]*?\.panel-header\.panel-header--has-search \.panel-header__top\s*\{[\s\S]*?display:\s*none;/,
  );
});

test("panel headers move mobile actions into a search-row overflow menu", () => {
  const panelHeader = source("../PanelHeader.tsx");

  assert.match(panelHeader, /MoreHorizontal/);
  assert.match(panelHeader, /<MoreHorizontal size=\{22\}/);
  assert.match(panelHeader, /flattenActionNodes/);
  assert.match(panelHeader, /panel-header__search-box/);
  assert.match(panelHeader, /panel-header__desktop-actions/);
  assert.match(panelHeader, /panel-header__mobile-actions/);
  assert.match(panelHeader, /panel-header__mobile-actions--search/);
  assert.match(panelHeader, /panel-header__mobile-more--inline/);
  assert.match(panelHeader, /panel-header__mobile-menu/);
  assert.match(panelHeader, /closest\("\[data-panel-header-dropdown\]"\)/);
  assert.match(panelHeader, /panel-header__search-accessory/);
  assert.match(panelHeader, /searchActions/);
  assert.match(panelHeader, /panel-header__search-actions/);
  assert.match(panelHeader, /panel-header--search-only/);
  assert.match(panelHeader, /panel-header__mobile-menu-accessory/);
  assert.doesNotMatch(panelHeader, /panel-header__mobile-primary/);
  assert.match(componentsCss, /\.panel-header__desktop-actions/);
  assert.match(componentsCss, /\.panel-header__mobile-actions/);
  assert.match(componentsCss, /\.panel-header__search-accessory/);
  assert.match(componentsCss, /\.panel-header__mobile-menu-accessory/);
  assert.match(
    componentsCss,
    /\.panel-header__actions > :is\(button, a, select\),[\s\S]*?\.panel-header__search-actions > \.flex > :is\(button, a, select\)\s*\{[\s\S]*?height:\s*2\.5rem;[\s\S]*?min-height:\s*2\.5rem;/,
  );
  assert.match(
    componentsCss,
    /\.panel-header__mobile-menu-accessory\s*>\s*:is\(\.relative, \.flex, \.panel-header-actions\),\s*\.panel-header__mobile-menu-item\s*>\s*:is\(\.relative, \.flex, \.panel-header-actions\)\s*\{[\s\S]*?display:\s*grid;[\s\S]*?width:\s*100%;[\s\S]*?gap:\s*0\.375rem;/,
  );
  const mobileMenuBlock = cssBlock(componentsCss, ".panel-header__mobile-menu");
  assert.match(
    mobileMenuBlock,
    /width:\s*min\(18rem,\s*calc\(100vw - 2rem\)\);/,
  );
  assert.match(mobileMenuBlock, /min-width:\s*0;/);
  assert.match(componentsCss, /\.panel-header__mobile-more > svg/);
  assert.match(
    componentsCss,
    /\.panel-header__mobile-more > svg\s*\{[\s\S]*?width:\s*1\.25rem;[\s\S]*?height:\s*1\.25rem;/,
  );
  assert.match(
    componentsCss,
    /\.panel-header__mobile-more--inline > svg\s*\{[\s\S]*?width:\s*1\.375rem;[\s\S]*?height:\s*1\.375rem;/,
  );
  assert.match(
    componentsCss,
    /\.panel-header__mobile-menu :is\(\.hidden, \.sm\\:inline\)\s*\{[\s\S]*?display:\s*inline-flex !important;/,
  );
  assert.match(
    componentsCss,
    /\.panel-header__mobile-menu-item > :is\(button, a\),[\s\S]*?\.panel-header__mobile-menu-accessory \[data-filter-menu\] > button\s*\{[\s\S]*?display:\s*flex;[\s\S]*?width:\s*100%;[\s\S]*?justify-content:\s*flex-start;/,
  );
  assert.match(
    componentsCss,
    /\.panel-header__mobile-menu-item[\s\S]*?> \.panel-header-actions[\s\S]*?\[data-filter-menu\][\s\S]*?\.panel-filter-trigger,[\s\S]*?\{[\s\S]*?display:\s*flex;[\s\S]*?width:\s*100%;[\s\S]*?justify-content:\s*flex-start;/,
  );
  assert.match(
    componentsCss,
    /\.panel-header__mobile-menu-item > :is\(button, a\),[\s\S]*?\.panel-header__mobile-menu-accessory \[data-filter-menu\] > button\s*\{[\s\S]*?height:\s*2\.5rem;[\s\S]*?background-color:\s*transparent !important;[\s\S]*?color:\s*var\(--theme-text\) !important;[\s\S]*?box-shadow:\s*none !important;/,
  );
  assert.match(
    componentsCss,
    /\.panel-header__mobile-menu-item > :is\(button, a\):hover,[\s\S]*?\.panel-header__mobile-menu-accessory \[data-filter-menu\] > button:hover\s*\{[\s\S]*?background-color:\s*color-mix\([\s\S]*?var\(--theme-primary\) 8%,[\s\S]*?transparent[\s\S]*?\) !important;/,
  );
  assert.match(
    componentsCss,
    /\.panel-header__mobile-menu-item > :is\(button, a\) > :is\(\.hidden, \.sm\\:inline\),[\s\S]*?\.panel-header__mobile-menu-accessory[\s\S]*?\[data-filter-menu\][\s\S]*?> button[\s\S]*?> :is\(\.hidden, \.sm\\:inline\)\s*\{[\s\S]*?flex:\s*1 1 auto;/,
  );
  assert.match(
    componentsCss,
    /\.panel-header__mobile-menu-item > :is\(button, a\) > svg:last-child,[\s\S]*?\.panel-header__mobile-menu-accessory[\s\S]*?\[data-filter-menu\][\s\S]*?> button[\s\S]*?> svg:last-child\s*\{[\s\S]*?margin-left:\s*auto;/,
  );
  assert.match(
    componentsCss,
    /\.panel-header__mobile-menu \.skill-filter-dropdown\s*\{[\s\S]*?position:\s*absolute;[\s\S]*?width:\s*100%;[\s\S]*?max-height:\s*min\(46dvh,\s*18rem\);[\s\S]*?overflow-y:\s*auto;/,
  );
  assert.match(
    componentsCss,
    /@media \(max-width:\s*639px\) \{[\s\S]*?\.panel-header__desktop-actions\s*\{[\s\S]*?display:\s*none;/,
  );
  assert.match(
    componentsCss,
    /@media \(max-width:\s*639px\) \{[\s\S]*?\.panel-header__mobile-actions\s*\{[\s\S]*?display:\s*flex;/,
  );
  assert.match(
    componentsCss,
    /@media \(max-width:\s*639px\) \{[\s\S]*?\.panel-header \.panel-header__search-box\s*\{[\s\S]*?position:\s*relative;/,
  );
  assert.match(
    componentsCss,
    /@media \(max-width:\s*639px\) \{[\s\S]*?\.panel-header__mobile-actions--search\s*\{[\s\S]*?position:\s*absolute;[\s\S]*?inset:\s*0;[\s\S]*?transform:\s*none;/,
  );
  assert.match(
    componentsCss,
    /@media \(max-width:\s*639px\) \{[\s\S]*?\.panel-header__mobile-actions--search \.panel-header__mobile-more\s*\{[\s\S]*?position:\s*absolute;[\s\S]*?right:\s*0\.125rem;/,
  );
  assert.match(
    componentsCss,
    /@media \(max-width:\s*639px\) \{[\s\S]*?\.panel-header__mobile-actions--search \.panel-header__mobile-menu\s*\{[\s\S]*?left:\s*0;[\s\S]*?right:\s*0;[\s\S]*?width:\s*100%;[\s\S]*?max-height:\s*min\(70dvh,\s*26rem\);/,
  );
  assert.match(
    componentsCss,
    /\.panel-header__mobile-more--inline\s*\{[\s\S]*?border:\s*0;[\s\S]*?background:\s*transparent;/,
  );
  assert.match(
    componentsCss,
    /@media \(max-width:\s*639px\) \{[\s\S]*?\.panel-header \.panel-header__search-accessory\s*\{[\s\S]*?display:\s*none;/,
  );
  assert.doesNotMatch(
    panelHeader,
    /className="btn-secondary panel-header__mobile-more/,
  );
});

test("panel filter dropdowns use viewport-clamped left positioning and refresh while open", () => {
  const panelControls = source("../PanelControls.tsx");

  assert.match(panelControls, /const updateDropdownPosition = \(\) => \{/);
  assert.match(panelControls, /const left = Math\.max\(/);
  assert.match(panelControls, /left,/);
  assert.doesNotMatch(panelControls, /right:\s*Math\.max/);
  assert.match(
    panelControls,
    /window\.addEventListener\("resize", updateDropdownPosition\)/,
  );
  assert.match(
    panelControls,
    /window\.addEventListener\("scroll", updateDropdownPosition, true\)/,
  );
});

test("panel header mounts search accessory only once while the mobile overflow menu is open", () => {
  const panelHeader = source("../PanelHeader.tsx");

  assert.match(
    panelHeader,
    /\{searchAccessory && !isMobileMenuOpen && \(/,
    "the search-row accessory should unmount while its mobile-menu copy is active",
  );
});

test("panel header dropdown portals are viewport-aware and do not collapse the parent mobile menu", () => {
  const scopeDropdown = source("../../persona/PersonaScopeDropdown.tsx");
  const tagDropdown = source("../../persona/PersonaTagFilterDropdown.tsx");
  const teamPanel = source("../../team/TeamBuilderWrapper.tsx");
  const personaPanel = source("../../persona/PersonaPlazaPanel.tsx");

  for (const file of [scopeDropdown, tagDropdown]) {
    assert.match(file, /data-panel-header-dropdown/);
    assert.match(file, /getDropdownPosition/);
    assert.match(file, /DROPDOWN_GUTTER/);
    assert.match(file, /window\.innerWidth/);
    assert.match(file, /onPointerDown=\{onClose\}/);
    assert.match(file, /onPointerDown=\{\(e\) => e\.stopPropagation\(\)\}/);
    assert.match(file, /event\.key === "Escape"/);
    assert.match(file, /role="menu"/);
  }

  assert.match(scopeDropdown, /role="menuitemradio"/);
  assert.match(scopeDropdown, /aria-checked=\{scopeFilter === key\}/);
  assert.match(tagDropdown, /aria-pressed=\{activeTag === tag\}/);

  for (const file of [teamPanel, personaPanel]) {
    assert.match(file, /aria-haspopup="menu"/);
    assert.match(file, /aria-expanded=\{isScopeOpen\}/);
    assert.match(file, /aria-expanded=\{isFilterOpen\}/);
  }
});

test("marketplace refresh action has a mobile menu label", () => {
  const marketplacePanel = source("../../panels/MarketplacePanel.tsx");

  assert.match(
    marketplacePanel,
    /<RotateCw size=\{16\} \/>\s*<span className="hidden sm:inline">\s*\{t\("common\.refresh"\)\}\s*<\/span>/,
  );
});

test("notification panel header aligns with shared panel spacing", () => {
  const notificationPanel = source("../../panels/NotificationPanel.tsx");

  assert.match(notificationPanel, /<PanelHeader/);
  assert.match(notificationPanel, /<Button[\s\S]*?variant="primary"/);
  assert.match(notificationPanel, /leftIcon=\{<Plus size=\{16\} \/>\}/);
  assert.doesNotMatch(
    notificationPanel,
    /inline-flex items-center gap-2 rounded-xl bg-stone-900 px-4 py-2\.5/,
  );
  assert.match(
    notificationPanel,
    /className="flex-1 overflow-y-auto px-4 py-2 sm:p-6 lg:px-8"/,
  );
  assert.match(
    notificationPanel,
    /className="glass-divider bg-transparent px-4 py-4 sm:px-6 lg:px-8"/,
  );
});

test("direct panel-search fields opt into the same refresh-safe behavior", () => {
  for (const path of [
    "../../panels/SettingsPanel.tsx",
    "../../team/RoleSquare.tsx",
  ]) {
    const file = source(path);
    assert.match(file, /PanelSearchInput/);
    assert.doesNotMatch(file, /<input[^>]*className="panel-search/);
  }

  for (const path of [
    "../../panels/MarketplacePanel.tsx",
    "../../panels/SkillsPanel/SkillsList.tsx",
  ]) {
    const file = source(path);
    assert.match(file, /PanelHeader/);
    assert.doesNotMatch(file, /<input[^>]*className="panel-search/);
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
    assert.match(file, /PanelSearchInput/);
    assert.doesNotMatch(
      file,
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
    assert.doesNotMatch(file, /if \(isLoading\)\s*\{\s*return <[^>]+Skeleton/);
    assert.match(file, /isInitialLoading/);
  }
});
