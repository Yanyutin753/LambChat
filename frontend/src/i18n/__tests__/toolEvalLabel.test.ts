import { readFileSync } from "node:fs";
import { resolve } from "node:path";

/**
 * eval 工具是 QuickJS REPL（运行代码取精确结果），
 * 面向用户的标签必须是「运行代码」语义，不能照字面直译成「评估」。
 */
function readLocale(locale: string): Record<string, unknown> {
  return JSON.parse(
    readFileSync(
      resolve(import.meta.dirname, "../locales", `${locale}.json`),
      "utf8",
    ),
  );
}

function toolEvalLabel(locale: string): string {
  const localeJson = readLocale(locale) as {
    chat?: { message?: Record<string, unknown> };
  };
  return localeJson.chat?.message?.toolEval as string;
}

test("zh eval tool label means running code, not literal evaluation", () => {
  expect(toolEvalLabel("zh")).toBe("运行代码");
});

test("all five locales keep the eval tool label in sync", () => {
  expect(toolEvalLabel("en")).toBe("Run code");
  expect(toolEvalLabel("ja")).toBe("コード実行");
  expect(toolEvalLabel("ko")).toBe("코드 실행");
  expect(toolEvalLabel("ru")).toBe("Выполнение кода");
});
