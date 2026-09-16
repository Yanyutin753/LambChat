import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = dirname(fileURLToPath(import.meta.url));
const localeDir = resolve(currentDir, "../../../../i18n/locales");

test("failed-requests insight surfaces the cancelled count when present", () => {
  const source = readFileSync(
    resolve(currentDir, "../InsightStrip.tsx"),
    "utf8",
  );

  // 取消不计入 failed_requests 后，失败卡片必须透出取消数，
  // 否则口径收窄在控制台上无法解释（字段算了却无处展示）
  expect(source).toMatch(/cancelled_requests \?\? 0/);
  expect(source).toMatch(/usage\.insight\.cancelledCount/);
  // 0 取消时不追加尾巴，保持原成功率先验文案
  expect(source).toMatch(/cancelled > 0/);
});

test("all five locales carry usage.insight.cancelledCount", () => {
  for (const locale of ["zh", "en", "ja", "ko", "ru"]) {
    const messages = JSON.parse(
      readFileSync(resolve(localeDir, `${locale}.json`), "utf8"),
    ) as { usage: { insight: Record<string, string> } };
    expect(
      messages.usage.insight.cancelledCount,
      `${locale} usage.insight.cancelledCount`,
    ).toBeTruthy();
    expect(messages.usage.insight.cancelledCount).toMatch(/\{\{count\}\}/);
  }
});
