import { readFileSync } from "node:fs";
import { resolve } from "node:path";

function readRepoFile(...segments: string[]): string {
  return readFileSync(
    resolve(import.meta.dirname, "../..", ...segments),
    "utf8",
  );
}

test("index.html 引导脚本预刷根字号，避免字体缩放首屏闪烁", () => {
  const html = readRepoFile("index.html");

  // 读取与 utils/fontScale.ts 相同的存储键
  expect(html).toMatch(/lambchat-font-scale/);
  // 在首屏渲染前写入 html 根字号
  expect(html).toMatch(
    /documentElement\.style\.fontSize\s*=\s*fontScaleRoots\[storedFontScale\]/,
  );
});

test("偏好设置 Tab 接入字体大小档位并持久化到用户 metadata", () => {
  const tab = readRepoFile(
    "src/components/profile/tabs/ProfilePreferencesTab.tsx",
  );

  expect(tab).toMatch(/FONT_SCALE_OPTIONS/);
  expect(tab).toMatch(/applyFontScaleToDocument/);
  expect(tab).toMatch(/updateMetadata\(\{ fontScale: scale \}\)/);
});

test("登录回灌时恢复字体大小偏好", () => {
  const restore = readRepoFile("src/hooks/userMetadataPreferences.ts");

  expect(restore).toMatch(/fontScale/);
  expect(restore).toMatch(/FONT_SCALE_EXTERNAL_CHANGE_EVENT/);
});
