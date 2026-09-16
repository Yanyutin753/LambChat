import { readFileSync } from "node:fs";
import { join } from "node:path";

// 护眼（sepia）主题只覆盖 --theme-* CSS 变量：theme-* 工具类随之变暖，
// 硬编码的 stone/white/red 亮色类不会适配，导致米黄底上出现冷灰色块
// （proto/profile-sepia-variants 分支原型评审结论，方案 A：纯 token 替换）。
// 本测试守护个人信息模块的文件：剥掉 dark: 前缀变体后，
// 浅色路径不得再出现硬编码中性色/红色工具类。

const sources = {
  "ProfileModal.tsx": readFileSync(
    join(import.meta.dirname, "../ProfileModal.tsx"),
    "utf8",
  ),
  "ProfileInfoTab.tsx": readFileSync(
    join(import.meta.dirname, "../tabs/ProfileInfoTab.tsx"),
    "utf8",
  ),
  "ProfileNotificationTab.tsx": readFileSync(
    join(import.meta.dirname, "../tabs/ProfileNotificationTab.tsx"),
    "utf8",
  ),
  "SandboxMachinesCard.tsx": readFileSync(
    join(import.meta.dirname, "../SandboxMachinesCard.tsx"),
    "utf8",
  ),
};

/** 去掉所有 dark: 前缀的工具类段（含 hover:dark: 等组合），只留浅色路径 */
function stripDarkVariants(source: string): string {
  return source.replace(/(?:[a-zA-Z-]+:)*dark:[^\s"'`{}]+/g, "");
}

// 红色只禁文字/边框类与浅底（red-50~400）；实心 bg-red-500/600 是危险
// CTA 的仓库既有约定（ui-button--danger 同为裸红），保留不动。
// 绿色同理整体禁用：状态色应走 --theme-success 等语义 token（sepia 降饱和）。
const BANNED_PATTERNS: { name: string; pattern: RegExp }[] = [
  { name: "stone-*", pattern: /(?:bg|text|border|ring|from|to|via)-stone-\d/ },
  { name: "border-white", pattern: /\bborder-white\b/ },
  {
    name: "red-*（文字/边框/浅底）",
    pattern:
      /(?:(?:hover:)?(?:text|border|ring)-(?:red|rose)-\d)|(?:bg-(?:red|rose)-[1-4]\d\b)/,
  },
  {
    name: "green-*（状态色请用 theme-success）",
    pattern: /(?:bg|text|border|ring)-(?:green|emerald)-\d/,
  },
];

test.each(Object.entries(sources))(
  "%s 浅色路径不依赖硬编码中性色/红色（护眼模式视觉统一）",
  (filename, source) => {
    const lightPath = stripDarkVariants(source);
    for (const { name, pattern } of BANNED_PATTERNS) {
      const match = lightPath.match(pattern);
      expect(
        match,
        `${filename} 浅色路径出现硬编码 ${name}（"${match?.[0]}"），` +
          `请改用 theme-* token 以适配护眼模式`,
      ).toBeNull();
    }
  },
);

// 语义色工具类依赖 tailwind.config 的 theme 色板映射；CSS 变量
// （--theme-success 等）在 tokens.css 里早已存在，但映射漏配时
// text-theme-error 这类类会静默不生成（颜色回退为继承值）。
const tailwindConfig = readFileSync(
  join(import.meta.dirname, "../../../../tailwind.config.js"),
  "utf8",
);

test.each([
  ["success", "var(--theme-success)"],
  ["error", "var(--theme-error)"],
  ["warning", "var(--theme-warning)"],
  ["info", "var(--theme-info)"],
])("tailwind theme 色板映射语义色 %s", (name, varRef) => {
  expect(tailwindConfig).toContain(`${name}: "${varRef}"`);
});
