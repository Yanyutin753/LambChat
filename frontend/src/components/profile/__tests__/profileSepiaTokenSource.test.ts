import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

// 护眼（sepia）主题只覆盖 --theme-* CSS 变量：theme-* 工具类随之变暖，
// 硬编码的 stone/slate/red/green 亮色类不会适配，导致米黄底上出现冷灰色块
// （proto/profile-sepia-variants 分支原型评审结论，方案 A：纯 token 替换）。
// 本测试自动枚举 profile 模块全部源文件（不含 __demo__/__tests__）：
// 剥掉 dark: 变体后，浅色路径不得出现硬编码中性色/状态色。

const PROFILE_DIR = join(import.meta.dirname, "..");

function listProfileSources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      return entry.name === "__demo__" || entry.name === "__tests__"
        ? []
        : listProfileSources(full);
    }
    return entry.name.endsWith(".tsx") || entry.name.endsWith(".ts")
      ? [full]
      : [];
  });
}

const sources: Record<string, string> = {};
for (const full of listProfileSources(PROFILE_DIR)) {
  sources[full.slice(PROFILE_DIR.length + 1)] = readFileSync(full, "utf8");
}

/** 去掉所有 dark: 前缀的工具类段（含 hover:dark: 等组合），只留浅色路径 */
function stripDarkVariants(source: string): string {
  return source.replace(/(?:[a-zA-Z-]+:)*dark:[^\s"'`{}]+/g, "");
}

// 红色只禁文字/边框类与浅底（red-50~400）；实心 bg-red-500/600 是危险
// CTA 的仓库既有约定（ui-button--danger 同为裸红），保留不动。
const BANNED_PATTERNS: { name: string; pattern: RegExp }[] = [
  {
    name: "stone/slate-*（冷灰中性色）",
    pattern: /(?:bg|text|border|ring|from|to|via)-(?:stone|slate)-[\d/]+/,
  },
  { name: "border-white", pattern: /\bborder-white\b/ },
  {
    name: "green-*（状态色请用 theme-success）",
    pattern: /(?:bg|text|border|ring)-(?:green|emerald)-[\d/]+/,
  },
  {
    name: "red-*（文字/边框/浅底）",
    pattern:
      /(?:(?:hover:)?(?:text|border|ring)-(?:red|rose)-[\d/]+)|(?:bg-(?:red|rose)-[1-4][\d/]*\b)/,
  },
];

test.each(Object.entries(sources))(
  "profile/%s 浅色路径不依赖硬编码中性色/状态色",
  (filename, source) => {
    const lightPath = stripDarkVariants(source);
    for (const { name, pattern } of BANNED_PATTERNS) {
      const match = lightPath.match(pattern);
      expect(
        match,
        `profile/${filename} 浅色路径出现硬编码 ${name}（"${match?.[0]}"），` +
          `请改用 theme-* token 以适配护眼模式`,
      ).toBeNull();
    }
  },
);

// 语义色工具类依赖 tailwind.config 的 theme 色板引用 CSS 变量
//（--theme-success 等）；映射漏配时 text-theme-error 之类会静默不生成
//（颜色回退为继承值）。只断言变量被引用（具体格式历经裸 var →
// color-mix 演进，不锁写法）。
const tailwindConfig = readFileSync(
  join(import.meta.dirname, "../../../../tailwind.config.js"),
  "utf8",
);

test.each([
  "var(--theme-success)",
  "var(--theme-error)",
  "var(--theme-warning)",
  "var(--theme-info)",
])("tailwind theme 色板引用语义色变量 %s", (varRef) => {
  expect(tailwindConfig).toContain(varRef);
});
