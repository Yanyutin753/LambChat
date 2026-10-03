import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const read = (path: string) =>
  readFileSync(new URL(path, import.meta.url), "utf8");

test("settled zero-output runs render an interrupted banner with retry entry", () => {
  const source = read("../index.tsx");
  expect(source).toContain("isInterruptedRunMessage");
  expect(source).toMatch(
    /isInterruptedRunMessage\(message\)[\s\S]{0,700}chat\.message\.runInterrupted/,
  );
  // 重试复用取消重试的按钮与回调链路
  expect(source).toMatch(
    /chat\.message\.runInterrupted[\s\S]{0,900}onRetryCancelledMessage\(message\.id\)/,
  );
  expect(source).toContain("chat-cancelled-retry");
});

test("runInterrupted copy exists in all five locales", () => {
  for (const locale of ["zh", "en", "ja", "ko", "ru"]) {
    const json = JSON.parse(
      read(`../../../../i18n/locales/${locale}.json`),
    );
    expect(json.chat.message.runInterrupted, locale).toBeTruthy();
  }
});
