import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";

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
  "../../plugins/feedback/FeedbackDialog.tsx",
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
  assert.match(hookSource, /export function useBodyScrollLock/);
  assert.match(
    hookSource,
    /const previousOverflow = document\.body\.style\.overflow/,
  );
  assert.match(hookSource, /document\.body\.style\.overflow = "hidden"/);
  assert.match(
    hookSource,
    /document\.body\.style\.overflow = previousOverflow/,
  );
});

test("selector modals use the shared body scroll lock hook", () => {
  for (const source of selectorSources) {
    assert.match(source, /useBodyScrollLock/);
    assert.doesNotMatch(source, /document\.body\.style\.overflow = "hidden"/);
  }
});

test("shared overlay surfaces use the shared body scroll lock hook", () => {
  for (const source of overlaySources) {
    assert.match(source, /useBodyScrollLock/);
    assert.doesNotMatch(source, /document\.body\.style\.overflow = "hidden"/);
  }
});
