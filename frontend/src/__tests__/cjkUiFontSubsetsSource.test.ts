import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

function readRepoFile(...segments: string[]): string {
  return readFileSync(
    resolve(import.meta.dirname, "../..", ...segments),
    "utf8",
  );
}

test("vite config registers vite-plugin-font for the serif family only", () => {
  const viteConfig = readRepoFile("vite.config.ts");

  expect(viteConfig).toMatch(/vite-plugin-font/);
  // VF name 表默认实例是 ExtraLight，不覆盖家族名则字体栈永远
  // 匹配不上；fontWeight 必须声明全区间让任意字重命中 VF 轴。
  expect(viteConfig).toMatch(/Font\.vite\(/);
  expect(viteConfig).toMatch(/fontFamily:\s*f\.family/);
  expect(viteConfig).toMatch(/fontWeight:\s*"100 900"/);
  expect(viteConfig).toMatch(/NotoSerifSC-VF/);
  // 黑体不接管 UI 中文：Noto Sans SC 的 600/700 比系统黑体重一截，
  // 接管后粗体观感发黑，仅保留衬线展示区的网页字体。
  expect(viteConfig).not.toMatch(/NotoSansSC-VF/);
});

test("CJK serif font loads via async chunk (fonts-cjk.ts) to keep it out of the critical CSS", () => {
  const main = readRepoFile("src/main.tsx");
  const fontsCjk = readRepoFile("src/fonts-cjk.ts");

  // 异步 import：数百条 @font-face 不进渲染阻塞的主 CSS，也不占
  // PWA 预缓存预算（预算守卫只放行路由壳 CSS）。
  expect(main).toMatch(/import\("\.\/fonts-cjk"\)/);
  expect(main).not.toMatch(/assets\/fonts\/Noto.*\.ttf";/);
  expect(fontsCjk).toMatch(
    /import\s+"\.\/assets\/fonts\/NotoSerifSC-VF\.ttf";/,
  );
  // 不带 ?subsets：全量分包 + languageAreas 频率打包；
  // ?subsets 模式未收录字符会退回系统字体、同段落出现混排。
  expect(fontsCjk).not.toMatch(/\?subsets/);
});

test("sans stack keeps system CJK fallbacks (no Noto Sans SC takeover)", () => {
  const config = readRepoFile("tailwind.config.js");
  const sansStack = config.match(/sans:\s*\[([\s\S]*?)\]/)?.[1] ?? "";
  const serifStack = config.match(/serif:\s*\[([\s\S]*?)\]/)?.[1] ?? "";

  expect(sansStack.indexOf("Source Sans 3")).toBeLessThan(
    sansStack.indexOf("system-ui"),
  );
  expect(sansStack).not.toContain("Noto Sans SC");
  expect(serifStack.indexOf("Source Serif 4")).toBeLessThan(
    serifStack.indexOf("Noto Serif SC"),
  );
  expect(serifStack.indexOf("Noto Serif SC")).toBeLessThan(
    serifStack.indexOf("Cambria"),
  );
});

test("root font-family routes CJK UI text to system fonts", () => {
  const tokens = readRepoFile("src/styles/tokens.css");
  const rootFamily =
    tokens.match(/:root\s*\{[^}]*font-family:\s*([^;]+);/s)?.[1] ?? "";

  expect(rootFamily.indexOf("Inter")).toBeLessThan(
    rootFamily.indexOf("system-ui"),
  );
  expect(rootFamily).not.toContain("Noto Sans SC");
});

test("serif variable font source is committed, sans source removed", () => {
  expect(
    existsSync(
      resolve(import.meta.dirname, "../../src/assets/fonts/NotoSerifSC-VF.ttf"),
    ),
  ).toBe(true);
  // 黑体 VF 已删（-17.7MB）：sans 中文走系统字体，防止误提交回流。
  expect(
    existsSync(
      resolve(import.meta.dirname, "../../src/assets/fonts/NotoSansSC-VF.ttf"),
    ),
  ).toBe(false);

  // cn-font-split 的 Rust 内核靠 postinstall 下载，pnpm v10 需在
  // pnpm-workspace.yaml 显式放行（package.json 的 pnpm 字段已废弃）
  const workspace = readRepoFile("pnpm-workspace.yaml");
  expect(workspace).toMatch(/onlyBuiltDependencies:/);
  expect(workspace).toMatch(/cn-font-split/);
});
