import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = dirname(fileURLToPath(import.meta.url));
const localesDir = resolve(currentDir, "../../../i18n/locales");
const tabSourcePath = resolve(currentDir, "../tabs/ProfilePreferencesTab.tsx");
const localSectionSourcePath = resolve(
  currentDir,
  "../LocalSandboxSection.tsx",
);

const locales = ["en", "zh", "ja", "ko", "ru"];

test("all locales label the merged sandbox card and its sub-sections", () => {
  for (const locale of locales) {
    const messages = JSON.parse(
      readFileSync(resolve(localesDir, `${locale}.json`), "utf8"),
    ) as {
      profile: Record<string, string> & {
        localSandbox: Record<string, string>;
      };
    };

    expect(messages.profile.sandbox).toBeTruthy();
    expect(messages.profile.cloudSandbox).toBeTruthy();
    expect(messages.profile.cloudSandboxDesc).toBeTruthy();
    expect(messages.profile.localSandbox.desc).toBeTruthy();
  }
});

test("preferences tab merges cloud and local sandbox into one card", () => {
  const source = readFileSync(tabSourcePath, "utf8");

  // 用户级存储：走 user metadata（同 memoryEnabled/defaultThinkingLevel 轨道）
  expect(source).toMatch(/sandboxCloudConfirmPolicy/);
  expect(source).toMatch(
    /authApi\.updateMetadata\(\{\s*sandboxCloudConfirmPolicy/,
  );
  // 一张「沙箱」卡：云端子区策略行 + 本地沙箱嵌入渲染（仍懒加载）
  expect(source).toMatch(/profile\.sandbox/);
  expect(source).toMatch(/profile\.cloudSandbox/);
  // 云端与本地共用同一行标签与同一组三档选项文案
  expect(source).toMatch(/profile\.localSandbox\.policy/);
  expect(source).toMatch(/profile\.localSandbox\.policyOptions/);
  expect(source).toMatch(/LocalSandboxSection embedded/);
});

test("local sandbox section supports embedded rendering without card chrome", () => {
  const source = readFileSync(localSectionSourcePath, "utf8");

  expect(source).toMatch(/embedded/);
});
