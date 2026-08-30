/**
 * 跨栈守门：后端 ErrorCode 枚举 ↔ 前端 5 个 locale 的 backendErrors.* 全覆盖。
 * 新增错误码而漏翻任何语言时，此测试直接失败。
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

type Locale = "en" | "zh" | "ja" | "ko" | "ru";
const LOCALES: Locale[] = ["en", "zh", "ja", "ko", "ru"];

const REPO_ROOT = join(__dirname, "../../../../");
const ERRORS_PY = join(REPO_ROOT, "src/kernel/errors.py");
const LOCALES_DIR = join(REPO_ROOT, "frontend/src/i18n/locales");

/** 从 src/kernel/errors.py 提取 (code, defaultMessage) 列表。 */
function extractErrorCodes(): Array<{ code: string; en: string }> {
  const source = readFileSync(ERRORS_PY, "utf-8");
  const pattern = /= \("([a-z0-9_]+)",\s*(\d+),\s*"((?:[^"\\]|\\.)*)"\)/g;
  const entries: Array<{ code: string; en: string }> = [];
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(source)) !== null) {
    entries.push({ code: match[1], en: match[3] });
  }
  if (entries.length === 0) {
    throw new Error("未能从 src/kernel/errors.py 提取到任何错误码，正则可能失效");
  }
  return entries;
}

function camel(code: string): string {
  return code.replace(/_([a-z0-9])/g, (_, c: string) => c.toUpperCase());
}

const enumEntries = extractErrorCodes();

test.each(LOCALES)("backendErrors 覆盖后端全部错误码（%s）", (locale) => {
  const data = JSON.parse(
    readFileSync(join(LOCALES_DIR, `${locale}.json`), "utf-8"),
  ) as Record<string, Record<string, string>>;
  const section = data.backendErrors ?? {};
  const missing = enumEntries
    .map((e) => camel(e.code))
    .filter((key) => !(key in section));
  expect(missing).toEqual([]);
});

test("backendErrors 无空文案", () => {
  for (const locale of LOCALES) {
    const data = JSON.parse(
      readFileSync(join(LOCALES_DIR, `${locale}.json`), "utf-8"),
    ) as Record<string, Record<string, string>>;
    const empty = Object.entries(data.backendErrors ?? {}).filter(
      ([, v]) => !v || !v.trim(),
    );
    expect(`${locale}: ${empty.map(([k]) => k).join(",")}`).toBe(`${locale}: `);
  }
});

test("en 文案不得残留中文（未翻译检查）", () => {
  const data = JSON.parse(
    readFileSync(join(LOCALES_DIR, "en.json"), "utf-8"),
  ) as Record<string, Record<string, string>>;
  const section = data.backendErrors ?? {};
  // locale 文案为人工审校副本、枚举 default_message 仅为无翻译时兜底，二者措辞允许不同；
  // 但 en locale 出现中文说明翻译遗漏。
  const cjk = Object.entries(section).filter(([, v]) => /[\u4e00-\u9fff]/.test(v));
  expect(cjk.map(([k]) => k)).toEqual([]);
});

test("插值占位符五语一致", () => {
  const sections = LOCALES.map((locale) =>
    (
      JSON.parse(
        readFileSync(join(LOCALES_DIR, `${locale}.json`), "utf-8"),
      ) as Record<string, Record<string, string>>
    ).backendErrors ?? {},
  );
  const placeholders = (s: string) =>
    Array.from(s.matchAll(/\{\{(\w+)\}\}/g))
      .map((m) => m[1])
      .sort()
      .join(",");
  const base = sections[0];
  const mismatched: string[] = [];
  for (const key of Object.keys(base)) {
    const expected = placeholders(base[key]);
    for (let i = 1; i < sections.length; i++) {
      if (sections[i][key] !== undefined && placeholders(sections[i][key]) !== expected) {
        mismatched.push(`${LOCALES[i]}.${key}`);
      }
    }
  }
  expect(mismatched).toEqual([]);
});
