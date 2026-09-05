import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = dirname(fileURLToPath(import.meta.url));
const localesDir = resolve(currentDir, "../../../i18n/locales");
const tabSourcePath = resolve(currentDir, "../tabs/ProfilePreferencesTab.tsx");

const locales = ["en", "zh", "ja", "ko", "ru"];

test("all locales label the cloud sandbox confirm policy preference", () => {
  for (const locale of locales) {
    const messages = JSON.parse(
      readFileSync(resolve(localesDir, `${locale}.json`), "utf8"),
    ) as { profile: Record<string, string> };

    expect(messages.profile.cloudSandboxPolicy).toBeTruthy();
  }
});

test("preferences tab persists the per-user cloud sandbox confirm policy", () => {
  const source = readFileSync(tabSourcePath, "utf8");

  // 用户级存储：走 user metadata（同 memoryEnabled/defaultThinkingLevel 轨道）
  expect(source).toMatch(/sandboxCloudConfirmPolicy/);
  expect(source).toMatch(/authApi\.updateMetadata\(\{\s*sandboxCloudConfirmPolicy/);
  // 三档策略与本地沙箱共用同一组选项文案
  expect(source).toMatch(/profile\.localSandbox\.policyOptions/);
  expect(source).toMatch(/"cloudSandboxPolicy"/);
});
