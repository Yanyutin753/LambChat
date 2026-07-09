import { readFileSync } from "node:fs";
function readSource(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

test("file operation pills render full file paths without path-breaking formatting", () => {
  const readFileItem = readSource("../ReadFileItem.tsx");
  const writeFileItem = readSource("../WriteFileItem.tsx");
  const editFileItem = readSource("../EditFileItem.tsx");
  const lsItem = readSource("../LsItem.tsx");

  expect(readFileItem).toMatch(
    /label=\{`\$\{t\("chat\.message\.toolRead"\)\} \$\{filePath \|\| ""\}`\}/,
  );
  expect(readFileItem).toMatch(/formatLabel=\{false\}/);

  expect(writeFileItem).toMatch(
    /label=\{`\$\{t\("chat\.message\.toolWrite"\)\} \$\{filePath \|\| ""\}`\}/,
  );
  expect(writeFileItem).toMatch(/formatLabel=\{false\}/);

  expect(editFileItem).toMatch(
    /label=\{`\$\{t\("chat\.message\.toolEdit"\)\} \$\{filePath \|\| ""\}`\}/,
  );
  expect(editFileItem).toMatch(/formatLabel=\{false\}/);

  expect(lsItem).toMatch(
    /label=\{`\$\{t\("chat\.message\.toolLs"\)\} \$\{dirPath\}`\}/,
  );
  expect(lsItem).toMatch(/formatLabel=\{false\}/);
});

test("collapsible pill always truncates labels to prevent overflow", () => {
  const source = readFileSync(
    new URL("../../../../common/CollapsiblePill.tsx", import.meta.url),
    "utf8",
  );

  expect(source).toMatch(/"font-mono min-w-0 truncate overflow-hidden[^"]*"/);
});

test("collapsible pill can preserve labels without path-breaking formatting", () => {
  const source = readFileSync(
    new URL("../../../../common/CollapsiblePill.tsx", import.meta.url),
    "utf8",
  );

  expect(source).toMatch(/formatLabel\?: boolean/);
  expect(source).toMatch(
    /const displayedLabel = formatLabel \? formattedLabel : label/,
  );
  expect(source).toMatch(/\{displayedLabel\}/);
});

test("collapsible pill uses a non-submit button for form-safe tool clicks", () => {
  const source = readFileSync(
    new URL("../../../../common/CollapsiblePill.tsx", import.meta.url),
    "utf8",
  );

  expect(source).toMatch(/<button[\s\S]*type="button"/);
});

test("ls tool panel has a stable key so repeated clicks keep the sidebar open", () => {
  const source = readSource("../LsItem.tsx");

  expect(source).toMatch(/panelKey:\s*`ls:\$\{dirPath\}`/);
});

test("ls tool opens from any non-empty result even when entries do not parse", () => {
  const source = readSource("../LsItem.tsx");

  expect(source).toMatch(/const rawText = extractText\(result\);/);
  expect(source).toMatch(/const canExpand = rawText\.trim\(\)\.length > 0;/);
});
