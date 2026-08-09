import { execFileSync } from "node:child_process";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = dirname(fileURLToPath(import.meta.url));
const frontendRoot = resolve(currentDir, "../../..");
const extractorPath = resolve(frontendRoot, "scripts/extract-i18n.ts");
const tsxPath = resolve(frontendRoot, "node_modules/.bin/tsx");

test("reports each newly extracted locale key once", () => {
  const fixtureDir = mkdtempSync(resolve(tmpdir(), "lambchat-i18n-extract-"));

  try {
    const localesDir = resolve(fixtureDir, "src/i18n/locales");
    mkdirSync(localesDir, { recursive: true });
    writeFileSync(
      resolve(fixtureDir, "src/Example.tsx"),
      'export function Example() { return t("example.newKey"); }\n',
    );

    for (const locale of ["en", "ja", "ko", "ru", "zh"]) {
      writeFileSync(resolve(localesDir, `${locale}.json`), "{}\n");
    }

    const output = execFileSync(tsxPath, [extractorPath], {
      cwd: fixtureDir,
      encoding: "utf8",
    });

    expect(
      output.match(/➕ Added to en\.json: example\.newKey/g) ?? [],
    ).toHaveLength(1);
  } finally {
    rmSync(fixtureDir, { recursive: true, force: true });
  }
});
