import { readFileSync } from "node:fs";
import { join } from "node:path";

const preferencesTabSource = readFileSync(
  join(process.cwd(), "src/components/profile/tabs/ProfilePreferencesTab.tsx"),
  "utf8",
);
const sectionSource = readFileSync(
  join(process.cwd(), "src/components/profile/LocalSandboxSection.tsx"),
  "utf8",
);
const appSource = readFileSync(join(process.cwd(), "src/App.tsx"), "utf8");

test("preferences tab lazy-loads the local sandbox section", () => {
  // PWA 预算（M4 T8）：本地沙箱分区（Tauri invoke 封装 + 配对表单）只有
  // 桌面壳用户才渲染——不得静态 import 进设置页所在的加载图。
  expect(preferencesTabSource).not.toMatch(/import \{ LocalSandboxSection \}/);
  expect(preferencesTabSource).toMatch(/lazy\(\(\) =>/);
  expect(preferencesTabSource).toMatch(/import\("\.\.\/LocalSandboxSection"\)/);
  expect(preferencesTabSource).toMatch(/<Suspense/);
});

test("local sandbox section keeps a default export for React.lazy", () => {
  // React.lazy 走默认导出；具名导出保留给既有组件测试。
  expect(sectionSource).toMatch(/export default LocalSandboxSection/);
  expect(sectionSource).toMatch(/export function LocalSandboxSection/);
});

test("web startup excludes the native updater and its dialog", () => {
  const updateShell = readFileSync(
    join(process.cwd(), "src/components/update/NativeUpdateShell.tsx"),
    "utf8",
  );
  expect(appSource).not.toMatch(/import \{ useAutoUpdate \}/);
  expect(appSource).toContain(
    'import("./components/update/NativeUpdateShell")',
  );
  expect(appSource).toContain('updatePlatform !== "web"');
  expect(updateShell).toContain('import("./UpdateDialog")');
  expect(updateShell).toMatch(
    /<Suspense fallback=\{null\}>[\s\S]*?<UpdateDialog/,
  );
});

test("mobile updater loading does not gate route mounting", () => {
  expect(appSource).toMatch(
    /<Suspense fallback=\{null\}>\s*<NativeUpdateShell\s+platform=\{updatePlatform\}\s+titlebarOs=\{null\}\s*\/>\s*<\/Suspense>\s*\)\}\s*\{appRoutes\}/,
  );
});
