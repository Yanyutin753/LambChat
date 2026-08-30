import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = dirname(fileURLToPath(import.meta.url));
const frontendSrc = resolve(currentDir, "../../../..");

function readJson(path: string) {
  return JSON.parse(readFileSync(path, "utf8"));
}

test("total cost is not shown directly in the action bar, only in the popover", () => {
  const source = readFileSync(resolve(currentDir, "../index.tsx"), "utf8");

  // 操作栏（点赞点踩一侧）不直接渲染金额，仅保留详情弹层
  expect(source).not.toMatch(/formatCostUsd\(message\.tokenUsage/);
  expect(source).not.toMatch(/hasPricedCost\(message\.tokenUsage\)/);
  // 弹层内仍由 TokenDetailsButton 渲染费用明细
  expect(source).toMatch(/fxRates=\{fxRates\}/);
  expect(source).toMatch(/language=\{i18n\.language\}/);
});

test("token details popover renders a cost breakdown section", () => {
  const source = readFileSync(resolve(currentDir, "../index.tsx"), "utf8");

  expect(source).toMatch(/priced && \(/);
  expect(source).toMatch(/costRows\.map/);
  expect(source).toMatch(/cost_breakdown|buildCostDetailRows/);
  expect(source).toMatch(/displayCurrency !== "USD"/);
  expect(source).toMatch(/t\("chat\.message\.costTotal"\)/);
});

test("cost total label is available in every locale", () => {
  for (const locale of ["en", "zh", "ja", "ko", "ru"]) {
    const messages = readJson(
      resolve(frontendSrc, "i18n", "locales", `${locale}.json`),
    ).chat.message;

    expect(typeof messages.costTotal).toBe("string");
    expect(messages.costTotal.trim()).not.toBe("");
  }
});
