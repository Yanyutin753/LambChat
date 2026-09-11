import { readFileSync } from "node:fs";

/**
 * 个人信息弹窗家族（外壳 + 偏好设置 tab + SelectRow + 内嵌沙箱分区）的
 * sepia 适配契约：亮色家族的中性 stone/白硬编码一律换成 theme-* token。
 * 亮色 token 值与原 stone 值一致（tokens.css 即按 stone 调色板定义），
 * 亮/暗渲染不变；sepia 由 .theme-sepia 的 token 覆盖层自动接管成暖色。
 * dark: 变体是暗色家族的显式声明，不属于本契约（校验前剥离）。
 */

const FAMILY_FILES = [
  "../ProfileModal.tsx",
  "../SelectRow.tsx",
  "../tabs/ProfilePreferencesTab.tsx",
  "../LocalSandboxSection.tsx",
  "../SandboxMachinesCard.tsx",
] as const;

/** 剥离 dark: 前缀类后，剩下的就是亮色/sepia 共享的亮色家族类 */
function lightFamilyClasses(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8").replace(
    /dark:[^\s"'`}]+/g,
    "",
  );
}

const LIGHT_FAMILY_NEUTRAL_HARDCODES =
  /\b(?:bg-white|bg-stone-(?:50|100|300)|border-stone-(?:100|200)|text-stone-(?:400|500|600|700|800|900))\b/g;

describe.each(FAMILY_FILES)("%s", (file) => {
  test("亮色家族不残留中性 stone/白硬编码（sepia 跟随 token）", () => {
    const offenders =
      lightFamilyClasses(file).match(LIGHT_FAMILY_NEUTRAL_HARDCODES) ?? [];
    expect(offenders).toEqual([]);
  });
});

test("弹窗外壳与下拉弹层表面走 theme token", () => {
  const modal = readFileSync(new URL("../ProfileModal.tsx", import.meta.url), "utf8");
  // 移动端抽屉 + 桌面弹窗两处壳，加桌面侧栏激活项，共三处同款表面
  expect(modal.match(/bg-theme-bg-card dark:bg-stone-800/g)?.length).toBe(3);
  // SelectRow 选中项：accent-light 亮色值即 amber-50，sepia 下暖米黄
  const selectRow = readFileSync(
    new URL("../SelectRow.tsx", import.meta.url),
    "utf8",
  );
  expect(selectRow).toMatch(/bg-theme-accent-light dark:bg-amber-900\/20/);
});
