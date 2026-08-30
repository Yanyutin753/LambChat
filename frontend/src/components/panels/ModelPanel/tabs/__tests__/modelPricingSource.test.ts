import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = dirname(fileURLToPath(import.meta.url));
const frontendSrc = resolve(currentDir, "../../../../..");

function readJson(path: string) {
  return JSON.parse(readFileSync(path, "utf8"));
}

test("model form exposes pricing override inputs and models.dev match hint", () => {
  const source = readFileSync(
    resolve(currentDir, "../ModelFormModal.tsx"),
    "utf8",
  );

  expect(source).toMatch(/formPriceInput/);
  expect(source).toMatch(/formPriceOutput/);
  expect(source).toMatch(/formPriceCacheRead/);
  expect(source).toMatch(/formPriceCacheWrite/);
  expect(source).toMatch(/pricingApi\s*\n?\s*\.lookup/);
  expect(source).toMatch(/pricingMatched/);
  expect(source).toMatch(/pricingUnmatched/);
});

test("model form persists pricing override and clears it with an empty object", () => {
  const source = readFileSync(
    resolve(currentDir, "../ModelFormModal.tsx"),
    "utf8",
  );

  expect(source).toMatch(/pricingOverride \?\? \{\}/);
  expect(source).toMatch(/priceInput !== undefined/);
});

test("model config toolbar has a manual pricing sync action", () => {
  const source = readFileSync(
    resolve(currentDir, "../ModelConfigTab.tsx"),
    "utf8",
  );

  expect(source).toMatch(/pricingApi\.sync\(\)/);
  expect(source).toMatch(/agentConfig\.pricingSync/);
});

test("pricing form labels are available in every locale", () => {
  for (const locale of ["en", "zh", "ja", "ko", "ru"]) {
    const messages = readJson(
      resolve(frontendSrc, "i18n", "locales", `${locale}.json`),
    ).agentConfig;

    for (const key of [
      "pricingLabel",
      "pricingInput",
      "pricingOutput",
      "pricingCacheRead",
      "pricingCacheWrite",
      "pricingMatched",
      "pricingUnmatched",
      "pricingHint",
      "pricingInvalid",
      "pricingSync",
      "pricingSyncSuccess",
      "pricingSyncFailed",
    ]) {
      expect(typeof messages[key]).toBe("string");
      expect(messages[key].trim()).not.toBe("");
    }
  }
});

test("api format selector is hidden for native anthropic/google protocols", () => {
  const source = readFileSync(
    resolve(currentDir, "../ModelFormModal.tsx"),
    "utf8",
  );

  expect(source).toMatch(/showsApiFormat\(modelProtocol\) && \(/);
  expect(source).toMatch(/resolveModelProtocol\(\{/);
});
