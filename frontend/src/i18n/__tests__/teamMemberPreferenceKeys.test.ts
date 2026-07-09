import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = dirname(fileURLToPath(import.meta.url));
const frontendSrc = resolve(currentDir, "../..");

const localeFiles = ["en", "zh", "ja", "ko", "ru"].map((locale) =>
  resolve(frontendSrc, "i18n", "locales", `${locale}.json`),
);

const teamMemberPreferenceKeys = [
  "followSessionModel",
  "memberModel",
  "memberModels",
  "runInSandbox",
  "runInSandboxTitle",
  "runInSandboxDesc",
  "enableSandbox",
  "disableSandbox",
];

function readJson(path: string) {
  return JSON.parse(readFileSync(path, "utf8"));
}

test("team member model and team sandbox strings are available in every locale", () => {
  for (const localeFile of localeFiles) {
    const locale = readJson(localeFile);

    for (const key of teamMemberPreferenceKeys) {
      expect(typeof locale.team[key]).toBe("string");
      expect(locale.team[key].trim()).not.toBe("");
    }
  }
});
