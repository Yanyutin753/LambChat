import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = dirname(fileURLToPath(import.meta.url));
const localesDir = resolve(currentDir, "../locales");

const LOCALES = ["en", "zh", "ja", "ko", "ru"];
const BASE_LOCALE = "en";

function readJson(path: string) {
  return JSON.parse(readFileSync(path, "utf8"));
}

/**
 * Recursively collect all dot-delimited key paths from a nested object.
 * e.g. { about: { title: "..." } } => ["about.title"]
 */
function collectKeys(obj: Record<string, unknown>, prefix = ""): string[] {
  const keys: string[] = [];
  for (const [key, value] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${key}` : key;
    if (typeof value === "object" && value !== null && !Array.isArray(value)) {
      keys.push(...collectKeys(value as Record<string, unknown>, fullKey));
    } else {
      keys.push(fullKey);
    }
  }
  return keys;
}

function getTopLevelKeys(obj: Record<string, unknown>): string[] {
  return Object.keys(obj).sort();
}

test("all locale files have the same top-level sections as en.json", () => {
  const enJson = readJson(resolve(localesDir, `${BASE_LOCALE}.json`));
  const enSections = getTopLevelKeys(enJson);

  for (const locale of LOCALES) {
    if (locale === BASE_LOCALE) continue;
    const localeJson = readJson(resolve(localesDir, `${locale}.json`));
    const localeSections = getTopLevelKeys(localeJson);

    const missing = enSections.filter((s) => !localeSections.includes(s));
    const extra = localeSections.filter((s) => !enSections.includes(s));

    if (missing.length > 0 || extra.length > 0) {
      throw new Error(
        `${locale}.json section mismatch:\n` +
          (missing.length > 0
            ? `  Missing sections: ${missing.join(", ")}\n`
            : "") +
          (extra.length > 0 ? `  Extra sections: ${extra.join(", ")}\n` : ""),
      );
    }
  }
});

test("all locale files have the same nested keys as en.json", () => {
  const enJson = readJson(resolve(localesDir, `${BASE_LOCALE}.json`));
  const enKeys = collectKeys(enJson).sort();

  for (const locale of LOCALES) {
    if (locale === BASE_LOCALE) continue;
    const localeJson = readJson(resolve(localesDir, `${locale}.json`));
    const localeKeys = collectKeys(localeJson).sort();

    const missing = enKeys.filter((k) => !localeKeys.includes(k));
    const extra = localeKeys.filter((k) => !enKeys.includes(k));

    if (missing.length > 0 || extra.length > 0) {
      throw new Error(
        `${locale}.json key mismatch (compared to ${BASE_LOCALE}.json):\n` +
          (missing.length > 0
            ? `  Missing keys (${missing.length}):\n    ${missing.join(
                "\n    ",
              )}\n`
            : "") +
          (extra.length > 0
            ? `  Extra keys (${extra.length}):\n    ${extra.join("\n    ")}\n`
            : ""),
      );
    }
  }
});

test("no locale file has empty string translations that differ from en.json empty values", () => {
  const enJson = readJson(resolve(localesDir, `${BASE_LOCALE}.json`));
  const enKeys = collectKeys(enJson);

  for (const locale of LOCALES) {
    if (locale === BASE_LOCALE) continue;
    const localeJson = readJson(resolve(localesDir, `${locale}.json`));

    for (const key of enKeys) {
      const parts = key.split(".");
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let enVal: any = enJson;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let localeVal: any = localeJson;
      for (const part of parts) {
        enVal = enVal[part];
        localeVal = localeVal[part];
      }

      // Non-string values (objects, numbers) are fine
      if (typeof enVal !== "string" || typeof localeVal !== "string") continue;

      // Skip keys that are intentionally the same across locales (e.g. agent names)
      if (
        enVal === localeVal ||
        enVal.startsWith("[TODO]") ||
        key.startsWith("agents.fast.") ||
        key.startsWith("agents.search.") ||
        key.startsWith("agents.team.")
      ) {
        continue;
      }

      // Flag values that look like they were copied from English without translation
      if (localeVal === enVal && enVal.length > 20) {
        throw new Error(
          `${locale}.json key "${key}" appears to be untranslated (same as English): "${enVal}"`,
        );
      }
    }
  }
});
