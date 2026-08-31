import { readFileSync } from "node:fs";
import { resolve } from "node:path";

/**
 * 各 panel 的标题级文字（卡片标题、弹窗标题、pane 标题、错误页大标题）
 * 必须与其他 panel 一致使用 font-serif。
 */
function readComponent(...segments: string[]): string {
  return readFileSync(
    resolve(import.meta.dirname, "../components", ...segments),
    "utf8",
  );
}

test("channel panel configuration card heading uses font-serif", () => {
  const source = readComponent("panels/ChannelPanel.tsx");
  expect(source).toMatch(
    /<h3 className="mb-4 text-sm font-semibold font-serif/,
  );
});

test("profile preferences dropdown title uses font-serif", () => {
  const source = readComponent("profile/tabs/ProfilePreferencesTab.tsx");
  expect(source).toMatch(
    /<h4 className="text-sm font-semibold font-serif/,
  );
});

test("team pane titles use font-serif like team member names", () => {
  const roster = readComponent("team/TeamRoster.tsx");
  const square = readComponent("team/RoleSquare.tsx");
  expect(roster.match(/team-pane-title font-serif/g)?.length).toBe(2);
  expect(square).toMatch(/team-pane-title font-serif/);
});

test("shared dialog titles use font-serif", () => {
  const confirm = readComponent("common/ConfirmDialog.tsx");
  const contact = readComponent("common/ContactAdminDialog.tsx");
  expect(confirm).toMatch(/text-base font-semibold font-serif/);
  expect(contact).toMatch(/text-base font-semibold font-serif tracking-tight/);
});

test("not found page headline uses font-serif like error boundary", () => {
  const source = readComponent("common/NotFoundPage.tsx");
  expect(source).toMatch(/text-2xl font-semibold font-serif/);
});

test("shared project error headline uses font-serif like shared page", () => {
  const source = readComponent("share/SharedProjectPage.tsx");
  expect(source).toMatch(/<h1 className="text-xl font-semibold font-serif/);
});

test("cad preview phase heading uses font-serif like its idle heading", () => {
  const source = readComponent("documents/previews/CadPreview.tsx");
  expect(source.match(/text-base font-medium font-serif/g)?.length).toBe(2);
});

test("skill preview modal files heading uses font-serif", () => {
  const source = readComponent("panels/MarketplacePanel/SkillPreviewModal.tsx");
  expect(source).toMatch(/text-sm font-semibold font-serif/);
});
