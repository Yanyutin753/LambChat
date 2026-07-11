import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const source = readFileSync(resolve(import.meta.dirname, "../index.ts"), "utf8");

test("i18n keeps the document language in sync with app language", () => {
  expect(source).toMatch(/function syncDocumentLanguage\(language: string\)/);
  expect(source).toMatch(/document\.documentElement\.lang = language\.split\("-"\)\[0\] \|\| "en"/);
  expect(source).toMatch(/const initialLanguage = detectLanguage\(\)/);
  expect(source).toMatch(/lng: initialLanguage/);
  expect(source).toMatch(/syncDocumentLanguage\(initialLanguage\)/);
  expect(source).toMatch(/i18n\.on\("languageChanged", syncDocumentLanguage\)/);
});
