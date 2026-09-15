import { existsSync, readFileSync } from "node:fs";

function readSource(relativePath: string): string {
  const url = new URL(relativePath, import.meta.url);
  return existsSync(url) ? readFileSync(url, "utf8") : "";
}

const tokensSource = readSource("../tokens.css");
const utilitiesSource = readSource("../utilities.css");
const mainActivitySource = readSource(
  "../../../android/app/src/main/java/com/lambchat/app/MainActivity.java",
);

// Android WebView 中 env(safe-area-inset-*) 恒为 0（即使 viewport-fit=cover），
// 系统栏遮挡只能靠原生注入的 --app-native-safe-area-* 变量兜底，
// 顶部与横向的前端变量必须与 env() 取 max 合并，二者缺一不可；
// 底部不预留安全区（产品决策：内容铺满到屏幕底边），恒为 0px。
test("safe-area variables merge env() with native injected insets on top and horizontal edges", () => {
  for (const edge of ["top", "left", "right"] as const) {
    expect(tokensSource).toMatch(
      new RegExp(
        `--app-safe-area-${edge}:\\s*max\\(\\s*env\\(safe-area-inset-${edge}, 0px\\),\\s*var\\(--app-native-safe-area-${edge}, 0px\\)\\s*\\)`,
      ),
    );
  }
  expect(tokensSource).toMatch(/--app-safe-area-bottom:\s*0px/);
  expect(tokensSource).not.toMatch(
    /--app-safe-area-bottom:\s*max\(\s*env\(safe-area-inset-bottom/,
  );
});

test("safe-area-x utility pads horizontal insets for landscape notches", () => {
  expect(utilitiesSource).toMatch(
    /\.safe-area-x\s*{[^}]*--app-safe-area-left[^}]*--app-safe-area-right/s,
  );
});

test("Android MainActivity injects system-bar insets as CSS variables", () => {
  expect(mainActivitySource).toMatch(/--app-native-safe-area-top/);
  expect(mainActivitySource).toMatch(/--app-native-safe-area-bottom/);
  expect(mainActivitySource).toMatch(/--app-native-safe-area-left/);
  expect(mainActivitySource).toMatch(/--app-native-safe-area-right/);
  expect(mainActivitySource).toMatch(
    /WindowInsetsCompat\.Type\.systemBars\(\)/,
  );
  expect(mainActivitySource).toMatch(
    /WindowInsetsCompat\.Type\.displayCutout\(\)/,
  );
  // 页面 reload 会清空 documentElement 上的内联变量，加载完成后必须重放注入
  expect(mainActivitySource).toMatch(/onPageFinished/);
});
