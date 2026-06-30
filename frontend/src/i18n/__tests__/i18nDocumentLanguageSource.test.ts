import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { resolve } from "node:path";

const source = readFileSync(resolve(import.meta.dirname, "../index.ts"), "utf8");

test("i18n keeps the document language in sync with app language", () => {
  assert.match(source, /function syncDocumentLanguage\(language: string\)/);
  assert.match(source, /document\.documentElement\.lang = language\.split\("-"\)\[0\] \|\| "en"/);
  assert.match(source, /const initialLanguage = detectLanguage\(\)/);
  assert.match(source, /lng: initialLanguage/);
  assert.match(source, /syncDocumentLanguage\(initialLanguage\)/);
  assert.match(source, /i18n\.on\("languageChanged", syncDocumentLanguage\)/);
});
