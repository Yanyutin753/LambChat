import { readFileSync } from "node:fs";
import ts from "typescript";
import { expect, test } from "vitest";

test("the UX preview entry point compiles without syntax errors", () => {
  const source = readFileSync(
    new URL("../../../scripts/panel-preview.ts", import.meta.url),
    "utf8",
  );
  const result = ts.transpileModule(source, {
    compilerOptions: { target: ts.ScriptTarget.ESNext },
    reportDiagnostics: true,
  });
  expect(result.diagnostics?.map((diagnostic) => diagnostic.messageText)).toEqual(
    [],
  );
});
