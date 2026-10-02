import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
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
  expect(
    result.diagnostics?.map((diagnostic) => diagnostic.messageText),
  ).toEqual([]);
});

test("native preview aliases skip dependency scanning and stay scoped to their components", () => {
  const source = readFileSync(
    new URL("../../../scripts/panel-preview.ts", import.meta.url),
    "utf8",
  );
  const parsed = ts.createSourceFile(
    "preview.ts",
    source,
    ts.ScriptTarget.Latest,
    true,
  );
  let resolveId: ts.MethodDeclaration | undefined;
  const visit = (node: ts.Node) => {
    if (
      ts.isMethodDeclaration(node) &&
      node.name.getText(parsed) === "resolveId"
    )
      resolveId = node;
    ts.forEachChild(node, visit);
  };
  visit(parsed);
  const method = resolveId!
    .getText(parsed)
    .replaceAll("import.meta.url", '"file:///preview/panel.ts"');
  const plugin = runInNewContext(ts.transpile(`({${method}})`), {
    URL,
    fileURLToPath: (url: URL) => url.pathname,
  });
  const sourceId = "../../services/tauri/sandboxShell";
  const local = "/components/profile/LocalSandboxSection.tsx";
  expect(plugin.resolveId(sourceId, local, { scan: true })).toBeUndefined();
  expect(plugin.resolveId(sourceId, local, {})).toBe(
    "/preview/local-sandbox-fixture.ts",
  );
  expect(
    plugin.resolveId(
      sourceId,
      "/components/profile/SandboxDataLocationCard.tsx",
      {},
    ),
  ).toBe("/preview/sandbox-location-fixture.ts");
  expect(
    plugin.resolveId(
      sourceId,
      "/components/profile/SandboxMachinesCard.tsx",
      {},
    ),
  ).toBeUndefined();
});

test("preview localizes the app bootstrap, JSON fixtures and live stream events", () => {
  const source = readFileSync(
    new URL("../../../scripts/panel-preview.ts", import.meta.url),
    "utf8",
  );
  expect(source).toContain("createPreviewLanguageBootstrap()");
  expect(source).toContain('resolvePreviewLanguage(previewParams.get("lang"))');
  expect(source).toContain(
    "JSON.stringify(localizePreviewData(value, language))",
  );
  expect(source).toMatch(/data: \$\{previewJson\(\{/);
  expect(source).toContain("response(url, scenario, chatState, language)");
});
