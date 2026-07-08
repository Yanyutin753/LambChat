import { existsSync, readFileSync } from "node:fs";
const wrapperSource = readFileSync(
  new URL("../TeamBuilderWrapper.tsx", import.meta.url),
  "utf8",
);
const builderSource = readFileSync(
  new URL("../TeamBuilder.tsx", import.meta.url),
  "utf8",
);
const memberCardSource = readFileSync(
  new URL("../TeamMemberCard.tsx", import.meta.url),
  "utf8",
);
const teamCssUrl = new URL("../../../styles/team.css", import.meta.url);
const teamCss = existsSync(teamCssUrl) ? readFileSync(teamCssUrl, "utf8") : "";

function cssBlock(selector: string) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return teamCss.match(new RegExp(`${escaped}\\s*\\{(?<body>[^}]*)\\}`))?.groups
    ?.body;
}

function assertCssDeclaration(
  selector: string,
  property: string,
  value: string,
) {
  expect(cssBlock(selector) ?? "").toMatch(
    new RegExp(`${property}:\\s*${value};`),
  );
}

test("team selected member cards fill the team member picker width", () => {
  assertCssDeclaration(".team-form-selected__list", "width", "100%");
  expect(teamCss).toMatch(
    /\.team-form-selected__list \.list-item-card\s*\{[\s\S]*?width:\s*100%;[\s\S]*?max-width:\s*none;/,
  );
});

test("team toggle keeps the desktop switch dimensions", () => {
  assertCssDeclaration(".team-toggle", "width", "36px");
  assertCssDeclaration(".team-toggle", "height", "20px");
  assertCssDeclaration(".team-toggle", "min-height", "20px");
  assertCssDeclaration(".team-toggle", "min-width", "36px");
  assertCssDeclaration(".team-toggle::after", "width", "16px");
  assertCssDeclaration(".team-toggle::after", "height", "16px");
  assertCssDeclaration(
    ".team-toggle--on::after",
    "transform",
    "translateX\\(16px\\)",
  );
});

test("team builder list adopts shared panel and role-library presentation", () => {
  expect(wrapperSource).toMatch(/<PanelHeader/);
  expect(wrapperSource).toMatch(/<EditorSidebar/);
  expect(wrapperSource).toMatch(/editorOpen/);
  expect(wrapperSource).toMatch(/widthStorageKey="team-editor-sidebar-width"/);
  expect(wrapperSource).toMatch(
    /skill-theme-shell flex h-full min-h-0 flex-col/,
  );
  expect(wrapperSource).toMatch(/skill-content-area flex-1 overflow-y-auto/);
  expect(wrapperSource).toMatch(/TEAM_PAGE_SIZE/);
  expect(wrapperSource).toMatch(/loadMoreRef/);
  expect(wrapperSource).toMatch(/IntersectionObserver/);
  expect(wrapperSource).toMatch(/className="team-card/);
  expect(wrapperSource).toMatch(/TeamAvatar/);
  expect(wrapperSource).toMatch(/getTeamFallbackAvatar/);
});

test("team builder relies on shared panel header mobile density", () => {
  expect(wrapperSource).toMatch(/<PanelHeader/);
  expect(wrapperSource).toMatch(/className="skill-panel-header"/);
  expect(wrapperSource).not.toMatch(/isHeaderCompact/);
  expect(wrapperSource).not.toMatch(/TEAM_HEADER_COMPACT_SCROLL_TOP/);
  expect(wrapperSource).not.toMatch(/handleContentScroll/);
  expect(wrapperSource).not.toMatch(/team-panel-header--compact/);
  expect(wrapperSource).not.toMatch(/onScroll=\{handleContentScroll\}/);
});

test("team editor uses one sidebar form matching role editor patterns", () => {
  expect(builderSource).toMatch(/className="es-form"/);
  expect(builderSource).toMatch(/ppe-profile-section/);
  expect(builderSource).toMatch(/tmb-header/);
  expect(builderSource).toMatch(/team-role-picker-trigger/);
  expect(builderSource).toMatch(/team-role-picker-dropdown__list/);
  expect(builderSource).toMatch(/team-form-selected__list/);
  expect(wrapperSource).toMatch(/footerState/);
  expect(wrapperSource).toMatch(/<EditorSidebar/);
  expect(builderSource).not.toMatch(/activeMobilePane/);
  expect(builderSource).not.toMatch(/team-builder-mobile-switch/);
  expect(builderSource).not.toMatch(/data-mobile-pane/);
  expect(builderSource).not.toMatch(/team-editor-progress/);
  expect(memberCardSource).toMatch(/list-item-card/);
  expect(memberCardSource).toMatch(/team-member-card__avatar-btn/);
  expect(builderSource).toMatch(/teamAvatar/);
  expect(builderSource).toMatch(/ppe-icon-picker/);
  expect(builderSource).toMatch(/persona-avatars/);
  expect(teamCss).toMatch(/\.team-editor-form\s*\{/);
  expect(teamCss).toMatch(/\.team-form-role-option\s*\{/);
  expect(teamCss).toMatch(/\.team-form-selected__list\s*\{/);
  expect(teamCss).toMatch(
    /\.team-form-selected__list \.list-item-card\s*\{[\s\S]*?width:\s*100%;/,
  );
  expect(teamCss).toMatch(/\.team-role-picker-dropdown\s*\{/);
});

test("team editor defines dedicated tablet and mobile adaptations", () => {
  expect(teamCss).toMatch(/@media \(max-width:\s*1180px\)/);
  expect(teamCss).toMatch(/@media \(max-width:\s*760px\)/);
  expect(builderSource).toMatch(/ppe-profile-section/);
  expect(teamCss).toMatch(/\.tmb-header/);
  expect(teamCss).toMatch(
    /@media \(max-width:\s*760px\) \{[\s\S]*?\.tmb-header\s*\{[\s\S]*?align-items:\s*stretch;/,
  );
  expect(teamCss).toMatch(
    /@media \(max-width:\s*760px\) \{[\s\S]*?\.tmb-header__row\s*\{[\s\S]*?flex-wrap:\s*wrap;/,
  );
  expect(teamCss).toMatch(
    /@media \(max-width:\s*760px\) \{[\s\S]*?\.team-editor-action-stack\s*\{[\s\S]*?min-width:\s*0;/,
  );
});

test("team styles allow long scrolling lists and compact mobile cards", () => {
  expect(teamCss).toMatch(/\.team-load-sentinel/);
  expect(teamCss).toMatch(/\.team-role-picker-dropdown__list/);
  expect(teamCss).toMatch(
    /\.team-role-picker-dropdown__list\s*\{[\s\S]*?overflow-y:\s*auto;/,
  );
  expect(teamCss).toMatch(
    /@media \(max-width:\s*639px\) \{[\s\S]*?\.team-form-role-list\s*\{[\s\S]*?max-height:\s*16rem;/,
  );
  expect(teamCss).toMatch(
    /@media \(max-width:\s*639px\) \{[\s\S]*?\.list-item-card__top\s*\{[\s\S]*?flex-wrap:\s*wrap;/,
  );
});

test("team avatar image containers constrain absolute avatar images", () => {
  for (const selector of [
    ".team-avatar",
    ".team-picker-avatar",
    ".team-toolbar-avatar",
  ]) {
    assertCssDeclaration(selector, "position", "relative");
    assertCssDeclaration(selector, "overflow", "hidden");
    assertCssDeclaration(selector, "flex-shrink", "0");
  }
  for (const selector of [".team-picker-avatar", ".team-toolbar-avatar"]) {
    expect(teamCss).toMatch(
      new RegExp(
        `${selector.replace(
          ".",
          "\\.",
        )} \\.scb__avatar-img\\s*,|,\\s*${selector.replace(
          ".",
          "\\.",
        )} \\.scb__avatar-img`,
      ),
    );
  }
  assertCssDeclaration(".team-picker-avatar", "width", "2\\.5rem");
  assertCssDeclaration(".team-picker-avatar", "height", "2\\.5rem");
  assertCssDeclaration(".team-toolbar-avatar", "width", "1\\.125rem");
  assertCssDeclaration(".team-toolbar-avatar", "height", "1\\.125rem");
});

test("team editor exposes team sandbox selection instead of member agent modes", () => {
  assert.match(builderSource, /runInSandbox/);
  assert.match(builderSource, /run_in_sandbox:\s*runInSandbox/);
  assert.match(builderSource, /team-sandbox-option/);
  assert.match(builderSource, /team\.run_in_sandbox/);
  assert.doesNotMatch(builderSource, /agentApi\s*\.\s*list\(\)/);
  assert.doesNotMatch(builderSource, /handleAgentChange/);
  assert.doesNotMatch(memberCardSource, /availableAgents/);
  assert.doesNotMatch(memberCardSource, /onAgentChange/);
  assert.doesNotMatch(memberCardSource, /followTeamMode/);
  assert.doesNotMatch(memberCardSource, /value=\{member\.agent_id \?\? ""\}/);
  assert.match(memberCardSource, /availableModels/);
  assert.match(memberCardSource, /onModelChange/);
  assert.match(memberCardSource, /team-member-card__model/);
  assert.match(memberCardSource, /followSessionModel/);
  assert.match(memberCardSource, /value=\{member\.model_id \?\? ""\}/);
  assert.match(memberCardSource, /onModelChange\?\.\(v \|\| null\)/);
  assert.match(teamCss, /\.team-member-card__model\s*\{/);
  assert.match(
    teamCss,
    /\.team-member-card__model span\s*\{[\s\S]*?text-overflow:\s*ellipsis;/,
  );
  assert.match(teamCss, /\.team-sandbox-option\s*\{/);
  assert.match(teamCss, /\.team-sandbox-option__title\s*\{/);
});
