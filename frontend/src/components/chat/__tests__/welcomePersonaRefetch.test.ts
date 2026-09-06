import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

/**
 * issue #158：角色广场（聊天内全屏弹窗）搜索/换页时，persona 列表重新加载
 * 会把 WelcomePage 整体换成骨架屏，连带卸载 ChatInput 与已打开的弹窗，
 * 用户视角即"直接跳转回首页"。本测试锁定整条接线：首次加载完成后，
 * 后台刷新不再回退骨架屏；弹窗分页窗口与父级请求页大小一致。
 */

const currentDir = dirname(fileURLToPath(import.meta.url));
const hookSource = readFileSync(
  resolve(currentDir, "../../../hooks/usePersonaPresets.ts"),
  "utf8",
);
const chatAppContentSource = readFileSync(
  resolve(currentDir, "../../layout/AppContent/ChatAppContent.tsx"),
  "utf8",
);
const chatViewPropsSource = readFileSync(
  resolve(currentDir, "../../layout/AppContent/ChatViewProps.tsx"),
  "utf8",
);
const chatViewSource = readFileSync(
  resolve(currentDir, "../../layout/AppContent/ChatView.tsx"),
  "utf8",
);
const welcomePageSource = readFileSync(
  resolve(currentDir, "../WelcomePage.tsx"),
  "utf8",
);

test("persona presets hook exposes a settled-first-fetch flag", () => {
  expect(hookSource).toMatch(/const \[hasLoaded, setHasLoaded\] = useState/);
  expect(hookSource).toMatch(/setHasLoaded\(true\);/);
  expect(hookSource).toMatch(/hasLoaded,/);
});

test("chat app content threads loaded flag and page size to chat view", () => {
  expect(chatAppContentSource).toMatch(/hasLoaded: personaPresetsLoaded,/);
  expect(chatAppContentSource).toMatch(
    /personaPresetsLoaded=\{personaPresetsLoaded\}/,
  );
});

test("chat view passes the loaded flag into the welcome page", () => {
  expect(chatViewPropsSource).toMatch(/personaPresetsLoaded: boolean;/);
  expect(chatViewSource).toMatch(
    /personaPresetsLoaded=\{personaPresetsLoaded\}/,
  );
  expect(welcomePageSource).toMatch(/personaPresetsLoaded\?: boolean;/);
});

test("welcome page readiness consults the loaded flag", () => {
  expect(welcomePageSource).toMatch(/personaPresetsLoaded,/);
  expect(welcomePageSource).toMatch(/personaPresetsLoaded,/);
  expect(welcomePageSource).toMatch(
    /isWelcomeContentReady\(\{[\s\S]*personaPresetsLoaded,[\s\S]*\}\)/,
  );
});

test("persona pagination window matches the selector page size", () => {
  // 弹窗 PAGE_SIZE=20；父级若按 12 取数，翻页窗口与页码标注错位且会漏行。
  expect(chatAppContentSource).toMatch(/const personaPresetPageSize = 20;/);
});
