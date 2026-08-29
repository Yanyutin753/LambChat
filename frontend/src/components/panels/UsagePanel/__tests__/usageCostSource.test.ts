import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = dirname(fileURLToPath(import.meta.url));
const frontendSrc = resolve(currentDir, "../../../..");

function readJson(path: string) {
  return JSON.parse(readFileSync(path, "utf8"));
}

test("usage panel shows a total cost KPI card", () => {
  const source = readFileSync(
    resolve(currentDir, "../../UsagePanel.tsx"),
    "utf8",
  );

  expect(source).toMatch(/usage\.costTotal/);
  expect(source).toMatch(/stats\.total_cost_usd/);
  expect(source).toMatch(/stats\.unpriced_requests/);
});

test("usage log table renders a cost column across desktop, tablet and mobile", () => {
  const source = readFileSync(
    resolve(currentDir, "../UsageLogsTable.tsx"),
    "utf8",
  );

  expect(source).toMatch(/usage\.cost/);
  expect(source).toMatch(/fmtCostUsd\(log\.cost_usd, Boolean\(log\.cost_available\)/);
  // 桌面网格、平板行、移动卡三处都要渲染费用
  expect(source.match(/fmtCostUsd\(log\.cost_usd/g)?.length).toBeGreaterThanOrEqual(3);
});

test("ranking rows show per-model cost", () => {
  const source = readFileSync(
    resolve(currentDir, "../RankingCards.tsx"),
    "utf8",
  );

  expect(source).toMatch(/item\.cost_usd \?\? 0/);
});

test("usage cost labels are available in every locale", () => {
  for (const locale of ["en", "zh", "ja", "ko", "ru"]) {
    const messages = readJson(
      resolve(frontendSrc, "i18n", "locales", `${locale}.json`),
    ).usage;

    for (const key of ["cost", "costTotal", "unpricedHint"]) {
      expect(typeof messages[key]).toBe("string");
      expect(messages[key].trim()).not.toBe("");
    }
  }
});
