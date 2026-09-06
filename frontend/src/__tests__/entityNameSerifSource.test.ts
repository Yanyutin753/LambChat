import { readFileSync } from "node:fs";
import { resolve } from "node:path";

/**
 * 名称类文案（agent/角色/persona/团队/模型/技能/会话/项目/用户名）
 * 与实体卡片标题一样统一使用 font-serif（Source Serif 4）。
 */
function readComponent(...segments: string[]): string {
  return readFileSync(
    resolve(import.meta.dirname, "../components", ...segments),
    "utf8",
  );
}

test("role selectors render role names with font-serif", () => {
  const selector = readComponent("panels/AgentPanel/shared/RoleSelector.tsx");
  expect(selector).toMatch(/flex items-center gap-2 font-serif/);
  expect(selector).toMatch(
    /<span className="font-serif">\{role\.name\}<\/span>/,
  );
  const square = readComponent("team/RoleSquare.tsx");
  expect(square).toMatch(/team-role-card__name font-serif/);
  const builder = readComponent("team/TeamBuilder.tsx");
  expect(builder).toMatch(/team-form-role-option__name font-serif/);
});

test("team member card renders agent and model names with font-serif", () => {
  const source = readComponent("team/TeamMemberCard.tsx");
  expect(source).toMatch(/font-serif">\{agentLabel\}/);
  expect(source).toMatch(/font-serif">\{modelLabel\}/);
  // 成员模式/成员模型下拉中的实体名同样 serif（富标签）
  expect(
    source.match(/className="font-serif"/g)?.length,
  ).toBeGreaterThanOrEqual(2);
});

test("mention popups render entity names with font-serif", () => {
  const persona = readComponent("chat/MentionPopup.tsx");
  const team = readComponent("chat/TeamMentionPopup.tsx");
  expect(persona).toMatch(/mention-popup-name font-serif/);
  expect(team).toMatch(/mention-popup-name font-serif/);
});

test("subagent and team tool results render member names with font-serif", () => {
  const subagent = readComponent("chat/ChatMessage/SubagentBlock.tsx");
  expect(subagent).toMatch(/text-13 font-medium font-serif truncate/);
  const teamItem = readComponent("chat/ChatMessage/items/TeamItem.tsx");
  expect(teamItem).toMatch(
    /text-xs text-theme-text font-semibold font-serif truncate/,
  );
  const picker = readComponent("team/TeamPickerModal.tsx");
  expect(picker).toMatch(/scb__mini-tag font-serif/);
});

test("channel selects render entity names with font-serif", () => {
  const agent = readComponent("panels/channel/ChannelAgentSelect.tsx");
  expect(agent).toMatch(/font-serif">\s*\{resolveAgentDisplayName/);
  const model = readComponent("panels/channel/ChannelModelSelect.tsx");
  expect(model).toMatch(/font-serif">\{model\.label\}/);
  const persona = readComponent("panels/channel/ChannelPersonaSelect.tsx");
  expect(persona.match(/truncate font-serif/g)?.length).toBe(2);
  const team = readComponent("panels/channel/ChannelTeamSelect.tsx");
  expect(team.match(/truncate font-serif/g)?.length).toBe(2);
  // 富标签需要 GlassSelect 支持 ReactNode label
  const glass = readComponent("common/GlassSelect.tsx");
  expect(glass).toMatch(/label: ReactNode/);
});

test("skill selectors render skill names with font-serif", () => {
  const skill = readComponent("selectors/SkillSelector.tsx");
  expect(skill).toMatch(/text-12 sm:text-13 font-medium font-serif truncate/);
  const personaEditor = readComponent("persona/PersonaEditorSkillSelector.tsx");
  expect(personaEditor).toMatch(/text-sm font-medium font-serif truncate/);
  const slash = readComponent("chat/SlashDropdownMenu.tsx");
  expect(slash).toMatch(/min-w-0 flex-1 truncate font-serif/);
});

test("sidebar session and project titles use font-serif", () => {
  const session = readComponent("sidebar/SessionItem.tsx");
  expect(session).toMatch(/truncate text-13 font-serif/);
  const project = readComponent("sidebar/ProjectItem.tsx");
  expect(project).toMatch(/truncate text-13 font-serif/);
  const mobileList = readComponent(
    "panels/SidebarParts/SessionListContent.tsx",
  );
  expect(mobileList).toMatch(/truncate font-serif">\s*\{project\.name\}/);
});

test("search and recent chat lists render session titles with font-serif", () => {
  const search = readComponent("panels/SearchDialog.tsx");
  expect(search).toMatch(/block text-sm font-serif text-stone-700/);
  expect(search).toMatch(/text-11 font-serif/);
  const recent = readComponent("sidebar/RecentChatsDialog.tsx");
  expect(recent).toMatch(/truncate text-13 font-serif/);
});

test("users panel renders usernames and role tags with font-serif", () => {
  const source = readComponent("panels/UsersPanel.tsx");
  expect(source.match(/font-medium font-serif text-theme-text/g)?.length).toBe(
    2,
  );
  expect(source.match(/tag tag-default font-serif/g)?.length).toBe(2);
});

test("settings panel group eyebrow matches profile serif eyebrow", () => {
  const source = readComponent("panels/SettingsPanel.tsx");
  expect(source).toMatch(
    /text-12 font-semibold font-serif uppercase tracking-wider/,
  );
});
