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
  expect(source).toMatch(
    /fmtCostUsd\(log\.cost_usd, log\.cost_available === true/,
  );
  // 桌面网格、平板行、移动卡三处都要渲染费用
  expect(source.match(/<LogCost log=\{log\}/g)?.length).toBeGreaterThanOrEqual(
    3,
  );
});

test("mobile usage card caps cost to 3 decimals", () => {
  const source = readFileSync(
    resolve(currentDir, "../UsageLogsTable.tsx"),
    "utf8",
  );

  // 手机端费用格空间窄，只保留 3 位小数；桌面/平板沿用默认精度
  expect(source).toMatch(/mobileCostOpts/);
  expect(source).toMatch(/maxDecimals: 3/);
  expect(source).toMatch(/<MobileCard[^>]*mobileCostOpts/s);
});

test("ranking rows show per-model cost", () => {
  const source = readFileSync(
    resolve(currentDir, "../RankingCards.tsx"),
    "utf8",
  );

  expect(source).toMatch(/fmtCostUsd\(item\.cost_usd, true/);
  expect(source).toMatch(/usageCostOptions\(item\)/);
});

test("usage log cache counts distinguish unknown from zero at every breakpoint", () => {
  const source = readFileSync(
    resolve(currentDir, "../UsageLogsTable.tsx"),
    "utf8",
  );
  expect(
    source.match(
      /formatUsageTokenCount\(\s*log,\s*"cache_read_tokens",\s*fmt,?\s*\)/g,
    ),
  ).toHaveLength(3);
});

test("usage cost labels are available in every locale", () => {
  for (const locale of ["en", "zh", "ja", "ko", "ru"]) {
    const messages = readJson(
      resolve(frontendSrc, "i18n", "locales", `${locale}.json`),
    ).usage;

    for (const key of [
      "cost",
      "costTotal",
      "unpricedHint",
      "historicalEstimate",
      "partialCostHint",
    ]) {
      expect(typeof messages[key]).toBe("string");
      expect(messages[key].trim()).not.toBe("");
    }
  }
});
