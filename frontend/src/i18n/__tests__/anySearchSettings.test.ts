import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

test.each(["zh", "en", "ja", "ko", "ru"])(
  "%s explains AnySearch key rotation in settings",
  (locale) => {
    const messages = JSON.parse(
      readFileSync(
        new URL(`../locales/${locale}.json`, import.meta.url),
        "utf8",
      ),
    );
    expect(messages.settingDesc.ANYSEARCH_API_KEYS).toContain("AnySearch");
  },
);
