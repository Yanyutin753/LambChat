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

test("app shell lazy-loads the update dialog", () => {
  // PWA 预算（M4 T8）：更新对话框只在「有新版本且用户未跳过」时渲染
  // （桌面/移动端专属 UI，含 UpdateProgressBar）——App 壳不得静态 import，
  // 否则五个 locale JSON 的增量会把 eager JS 推过 512000 预算。
  expect(appSource).not.toMatch(
    /import \{ UpdateDialog \} from "\.\/components\/update\/UpdateDialog"/,
  );
  expect(appSource).toMatch(/import\("\.\/components\/update\/UpdateDialog"\)/);
  // 懒组件必须包 Suspense（fallback null：对话框按需挂载）
  expect(appSource).toMatch(
    /<Suspense fallback=\{null\}>[\s\S]*?<UpdateDialog/,
  );
});
