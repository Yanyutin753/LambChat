import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = dirname(fileURLToPath(import.meta.url));
const localesDir = resolve(currentDir, "../locales");

const LOCALES = ["en", "zh", "ja", "ko", "ru"];
const REMOVED_PROMPT_CACHE_SETTINGS = [
  "PROMPT_CACHE_MAX_SYSTEM_BLOCKS",
  "PROMPT_CACHE_MAX_TOOLS",
];

test.each(LOCALES)(
  "%s locale omits obsolete prompt cache setting descriptions",
  (locale) => {
    const messages = JSON.parse(
      readFileSync(resolve(localesDir, `${locale}.json`), "utf8"),
    ) as { settingDesc: Record<string, unknown> };

    for (const settingName of REMOVED_PROMPT_CACHE_SETTINGS) {
      expect(messages.settingDesc).not.toHaveProperty(settingName);
    }
  },
);
