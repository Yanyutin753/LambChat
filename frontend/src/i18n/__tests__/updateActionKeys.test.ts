import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = dirname(fileURLToPath(import.meta.url));
const localesDir = resolve(currentDir, "../locales");
const componentsDir = resolve(currentDir, "../../components");
const locales = ["en", "zh", "ja", "ko", "ru"];

/** 更新 UI（标题栏指示器 / UpdateDialog）的主按钮与状态文案 key。
 * updateRelaunchInstall 只有 update.* 命名空间内的条目——引用成顶层
 * key 时五语全部 miss，非中文用户会看到中文 defaultValue 兜底。 */
const namespacedKeys = ["updateRelaunchInstall", "availableTitle", "skipVersion", "viewFullNotes"];
const topLevelKeys = [
  "updateDownloading",
  "updateError",
  "updateGoToDownload",
  "updateDownloadAndInstall",
  "updateDownload",
  "updatePublishedAt",
  "updateRetry",
];

test("all locales carry the update action labels the update UI references", () => {
  for (const locale of locales) {
    const messages = JSON.parse(
      readFileSync(resolve(localesDir, `${locale}.json`), "utf8"),
    ) as Record<string, unknown> & { update: Record<string, string> };

    for (const key of namespacedKeys) {
      expect(messages.update[key], `${locale} update.${key}`).toBeTruthy();
    }
    for (const key of topLevelKeys) {
      expect(messages[key], `${locale} ${key}`).toBeTruthy();
    }
  }
});

test("update UI references the namespaced relaunch-install key, not a missing top-level one", () => {
  for (const component of [
    "layout/TitleBar/UpdateTitlebarIndicator.tsx",
    "update/UpdateDialog.tsx",
  ]) {
    const source = readFileSync(resolve(componentsDir, component), "utf8");
    expect(source, component).toContain('t("update.updateRelaunchInstall"');
    expect(source, component).not.toContain('t("updateRelaunchInstall"');
  }
});
