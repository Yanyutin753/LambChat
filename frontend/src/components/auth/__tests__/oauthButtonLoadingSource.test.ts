import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const currentDir = dirname(fileURLToPath(import.meta.url));

function readAuthSource(fileName: string): string {
  return readFileSync(join(currentDir, fileName), "utf8");
}

test("oauth provider buttons enter a loading state immediately on click", () => {
  const authPage = readAuthSource("../AuthPage.tsx");

  // 点击即记录 pending 提供商；失败才复位（成功路径页面直接跳走）
  expect(authPage).toMatch(/oauthPendingProvider/);
  expect(authPage).toMatch(
    /setOauthPendingProvider\(provider\);[\s\S]*?await loginWithOAuth\(provider\)/,
  );
  expect(authPage).toMatch(/catch[\s\S]*?setOauthPendingProvider\(null\)/);

  // pending 期间所有 OAuth 按钮禁用，防止连点重复跳转
  expect(authPage).toMatch(/disabled=\{oauthPendingProvider !== null\}/);

  // 被点击的按钮图标位换成旋转 spinner
  expect(authPage).toMatch(
    /oauthPendingProvider === provider\.id[\s\S]*?animate-spin/,
  );
});
