import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

// These forms own drafts in useState; changing the record must change their identity.
test.each([
  [
    "ModelPanel/tabs/ModelConfigTab.tsx",
    "ModelFormModal",
    'editingModel?.id ?? "new"',
  ],
  ["NotificationPanel.tsx", "NotificationFormModal", "editingNotification.id"],
  ["ScheduledTaskPanel/index.tsx", "TaskFormModal", "editingTask.id"],
])("%s gives retained editors a record identity", (file, component, key) => {
  const source = readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
  expect(source).toContain(
    `<${component}\n${" ".repeat(
      component === "TaskFormModal" ? 14 : 10,
    )}key={${key}}`,
  );
});
