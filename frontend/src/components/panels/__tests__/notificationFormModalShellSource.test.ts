import { readFileSync } from "node:fs";
import { join } from "node:path";

const notificationPanelSource = readFileSync(
  join(import.meta.dirname, "../NotificationPanel.tsx"),
  "utf8",
);

test("notification create/edit form reuses the shared EditorSidebar shell", () => {
  // 与 TaskFormModal / ModelFormModal / GithubImportModal 一致：表单弹窗走共享父组件
  expect(notificationPanelSource).toMatch(
    /import \{ EditorSidebar \} from "\.\.\/common\/EditorSidebar";/,
  );
  expect(notificationPanelSource).toMatch(/<EditorSidebar/);
  expect(notificationPanelSource).toMatch(/open=\{true\}/);
  expect(notificationPanelSource).toMatch(/onClose=\{onClose\}/);
  expect(notificationPanelSource).toMatch(/footer=\{/);
  expect(notificationPanelSource).toMatch(/<PanelFooterActions>/);
});

test("notification form body uses shared es-form field utilities", () => {
  expect(notificationPanelSource).toMatch(/className="es-form"/);
  expect(notificationPanelSource).toMatch(/es-field/);
  expect(notificationPanelSource).toMatch(/es-label/);
});

test("notification active toggle reuses the shared ToggleSwitch", () => {
  expect(notificationPanelSource).toMatch(
    /import \{ ToggleSwitch \} from "\.\/AgentPanel\/shared";/,
  );
  expect(notificationPanelSource).toMatch(/<ToggleSwitch/);
  expect(notificationPanelSource).not.toMatch(
    /rounded-full border-2 border-transparent transition-colors/,
  );
});

test("notification form no longer hand-rolls its own modal overlay", () => {
  expect(notificationPanelSource).not.toMatch(/fixed inset-0/);
  expect(notificationPanelSource).not.toMatch(/bg-black\/50/);
  expect(notificationPanelSource).not.toMatch(/max-w-2xl/);
});
