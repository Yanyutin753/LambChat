import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = dirname(fileURLToPath(import.meta.url));
const frontendSrc = resolve(currentDir, "../../../..");

function readJson(path: string) {
  return JSON.parse(readFileSync(path, "utf8"));
}

test("message action bar shows the total cost directly without opening the popover", () => {
  const source = readFileSync(resolve(currentDir, "../index.tsx"), "utf8");

  expect(source).toMatch(/hasPricedCost\(message\.tokenUsage\)/);
  expect(source).toMatch(/formatCostUsd\(message\.tokenUsage\?\.cost_usd/);
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
