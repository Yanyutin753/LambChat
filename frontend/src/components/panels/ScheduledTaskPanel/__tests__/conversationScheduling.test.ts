import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

for (const locale of ["zh", "en", "ja", "ko", "ru"]) {
  test(`${locale} exposes conversation scheduling text at the rendered namespace`, () => {
    const messages = JSON.parse(
      readFileSync(
        new URL(`../../../../i18n/locales/${locale}.json`, import.meta.url),
        "utf8",
      ),
    );
    for (const key of [
      "executionMode",
      "conversationMode",
      "standaloneMode",
      "targetConversation",
      "targetRequired",
      "currentConversation",
      "inheritContext",
      "notificationPolicy",
      "meaningfulChanges",
      "alwaysNotify",
      "openConversation",
      "noUpdate",
    ]) {
      expect(messages.scheduledTask[key], key).toBeTypeOf("string");
    }
  });
}

test("scheduled tasks stay accessible from the sidebar without a chat header shortcut", () => {
  const source = readFileSync(
    new URL("../../../layout/AppContent/Header.tsx", import.meta.url),
    "utf8",
  );
  expect(source).not.toContain("SessionScheduledTasksButton");
  const sidebar = readFileSync(
    new URL("../../SidebarParts/SidebarRail.tsx", import.meta.url),
    "utf8",
  );
  expect(sidebar).toContain("onClick={onOpenScheduledTasks}");
  expect(sidebar).toContain('aria-label={t("nav.scheduled-tasks")}');
});
