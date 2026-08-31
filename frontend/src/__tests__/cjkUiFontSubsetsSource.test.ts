import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

function readRepoFile(...segments: string[]): string {
  return readFileSync(
    resolve(import.meta.dirname, "../..", ...segments),
    "utf8",
  );
}

test("vite config registers vite-plugin-font per family with family overrides", () => {
  const viteConfig = readRepoFile("vite.config.ts");

  expect(viteConfig).toMatch(/vite-plugin-font/);
  // VF name 表默认实例是 Thin/ExtraLight，不覆盖家族名则字体栈永远
  // 匹配不上；fontWeight 必须声明全区间让任意字重命中 VF 轴。
  expect(viteConfig).toMatch(/Font\.vite\(/);
  expect(viteConfig).toMatch(/fontFamily:\s*f\.family/);
  expect(viteConfig).toMatch(/fontWeight:\s*"100 900"/);
  expect(viteConfig).toMatch(/NotoSansSC-VF/);
  expect(viteConfig).toMatch(/NotoSerifSC-VF/);
});

test("CJK fonts load via async chunk (fonts-cjk.ts) to keep them out of the critical CSS", () => {
  const main = readRepoFile("src/main.tsx");
  const fontsCjk = readRepoFile("src/fonts-cjk.ts");

  // 异步 import：~660 条 @font-face 不进渲染阻塞的主 CSS，也不占
  // PWA 预缓存预算（预算守卫只放行路由壳 CSS）。
  expect(main).toMatch(/import\("\.\/fonts-cjk"\)/);
  expect(main).not.toMatch(/assets\/fonts\/Noto.*\.ttf";/);
  for (const f of ["NotoSansSC-VF", "NotoSerifSC-VF"]) {
    expect(fontsCjk).toMatch(new RegExp(`import\\s+"\\./assets/fonts/${f}\\.ttf";`));
  }
  // 不带 ?subsets：全量分包 + languageAreas 频率打包，覆盖聊天内容；
  // ?subsets 模式未收录字符会退回系统字体、同段落出现混排。
  expect(fontsCjk).not.toMatch(/\?subsets/);
});

test("font stacks prefer the subset webfonts over system CJK fallbacks", () => {
  const config = readRepoFile("tailwind.config.js");
  const sansStack = config.match(/sans:\s*\[([\s\S]*?)\]/)?.[1] ?? "";
  const serifStack = config.match(/serif:\s*\[([\s\S]*?)\]/)?.[1] ?? "";

  expect(sansStack.indexOf("Source Sans 3")).toBeLessThan(
    sansStack.indexOf("Noto Sans SC"),
  );
  expect(sansStack.indexOf("Noto Sans SC")).toBeLessThan(
    sansStack.indexOf("system-ui"),
  );
  expect(serifStack.indexOf("Source Serif 4")).toBeLessThan(
    serifStack.indexOf("Noto Serif SC"),
  );
  expect(serifStack.indexOf("Noto Serif SC")).toBeLessThan(
    serifStack.indexOf("Cambria"),
  );
});

test("root font-family routes CJK UI text into the sans subset", () => {
  const tokens = readRepoFile("src/styles/tokens.css");
  const rootFamily = tokens.match(
    /:root\s*\{[^}]*font-family:\s*([^;]+);/s,
  )?.[1] ?? "";

  expect(rootFamily.indexOf("Inter")).toBeLessThan(
    rootFamily.indexOf('"Noto Sans SC"'),
  );
  expect(rootFamily.indexOf('"Noto Sans SC"')).toBeLessThan(
    rootFamily.indexOf("system-ui"),
  );
});

test("variable font sources are committed and native build scripts allowed", () => {
  for (const f of ["NotoSansSC-VF.ttf", "NotoSerifSC-VF.ttf"]) {
    expect(
      existsSync(resolve(import.meta.dirname, `../../src/assets/fonts/${f}`)),
    ).toBe(true);
  }

  // cn-font-split 的 Rust 内核靠 postinstall 下载，pnpm v10 需在
  // pnpm-workspace.yaml 显式放行（package.json 的 pnpm 字段已废弃）
  const workspace = readRepoFile("pnpm-workspace.yaml");
  expect(workspace).toMatch(/onlyBuiltDependencies:/);
  expect(workspace).toMatch(/cn-font-split/);
});
