import { readFileSync } from "node:fs";

/** 版本展示纪律（源码结构断言）：客户端展示的「当前版本」一律是打包进
 *  bundle 的 APP_VERSION（客户端自身版本），不得拿服务端 /api/version 的
 *  app_version 冒充——桌面端/移动端看到的应该是自己是什么版本。服务端
 *  versionInfo 只用于 latest_version / has_update 等更新对比信息。 */

function readSource(relativePath: string): string {
  const url = new URL(relativePath, import.meta.url);
  return readFileSync(url, "utf8");
}

test("profile modal footer shows the bundled client version", () => {
  const source = readSource("../ProfileModal.tsx");
  expect(source).toMatch(/APP_VERSION/);
  expect(source).not.toMatch(/versionInfo\.app_version/);
  expect(source).not.toMatch(/versionInfo\?\.app_version/);
});

test("about dialog current version shows the bundled client version", () => {
  const source = readSource("../../common/AboutDialog.tsx");
  expect(source).toMatch(/APP_VERSION/);
  expect(source).not.toMatch(/versionInfo\.app_version/);
});

test("initial version fetch reports the client version for has_update", () => {
  // 首次 get() 也带 client_version：has_update 按客户端版本比较，
  // 而不是服务端版本（网页端服务端=客户端，桌面端两者可能相差多个版本）。
  const source = readSource("../../../hooks/useVersion.ts");
  expect(source).toMatch(/versionApi\.get\(\s*APP_VERSION\s*\)/);
});

test("app content no longer threads server versionInfo into the profile modal", () => {
  const source = readSource("../../layout/AppContent/index.tsx");
  expect(source).not.toMatch(/versionInfo/);
  expect(source).not.toMatch(/useVersion/);
});
