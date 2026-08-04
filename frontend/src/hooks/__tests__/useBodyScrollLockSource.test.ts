import { existsSync, readFileSync } from "node:fs";
function readSource(relativePath: string): string {
  const url = new URL(relativePath, import.meta.url);
  return existsSync(url) ? readFileSync(url, "utf8") : "";
}

const hookSource = readSource("../useBodyScrollLock.ts");
const selectorSources = [
  "../../components/selectors/AgentModeSelector.tsx",
  "../../components/selectors/SkillSelector.tsx",
  "../../components/selectors/ToolSelector.tsx",
].map(readSource);
const overlaySources = [
  "../../components/chat/ChatMessage/FeedbackDialog.tsx",
  "../../components/chat/ChatInputExpandedComposer.tsx",
  "../../components/common/ConfirmDialog.tsx",
  "../../components/common/ContactAdminDialog.tsx",
  "../../components/common/DeleteProjectDialog.tsx",
  "../../components/common/ImageViewer.tsx",
  "../../components/common/VideoViewer.tsx",
  "../../components/profile/ProfileModal.tsx",
  "../../components/share/ShareDialog.tsx",
  "../../components/sidebar/SessionPreviewDialog.tsx",
  "../../components/team/TeamPickerModal.tsx",
].map(readSource);

test("useBodyScrollLock preserves and restores the previous body overflow value", () => {
  expect(hookSource).toMatch(/export function useBodyScrollLock/);
  expect(hookSource).toMatch(
    /const previousOverflow = document\.body\.style\.overflow/,
  );
  expect(hookSource).toMatch(/document\.body\.style\.overflow = "hidden"/);
  expect(hookSource).toMatch(
    /document\.body\.style\.overflow = previousOverflow/,
  );
});

test("selector modals use the shared body scroll lock hook", () => {
  for (const source of selectorSources) {
    expect(source).toMatch(/useBodyScrollLock/);
    expect(source).not.toMatch(/document\.body\.style\.overflow = "hidden"/);
  }
});

test("shared overlay surfaces use the shared body scroll lock hook", () => {
  for (const source of overlaySources) {
    expect(source).toMatch(/useBodyScrollLock/);
    expect(source).not.toMatch(/document\.body\.style\.overflow = "hidden"/);
  }
});
