import { execFileSync } from "node:child_process";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = dirname(fileURLToPath(import.meta.url));
const frontendRoot = resolve(currentDir, "../../..");
const extractorPath = resolve(frontendRoot, "scripts/extract-i18n.ts");
// Windows 下 .bin/tsx 是无扩展名 shell 脚本，execFileSync 直接 spawn 会 ENOENT；
// 统一走 node + tsx CLI 入口，跨平台一致。
const tsxPath = resolve(frontendRoot, "node_modules/tsx/dist/cli.mjs");

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

    const output = execFileSync(process.execPath, [tsxPath, extractorPath], {
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

test("extracts keys from .ts hook files but skips __tests__ fixtures", () => {
  const fixtureDir = mkdtempSync(resolve(tmpdir(), "lambchat-i18n-extract-"));

  try {
    const localesDir = resolve(fixtureDir, "src/i18n/locales");
    mkdirSync(resolve(fixtureDir, "src/hooks"), { recursive: true });
    mkdirSync(resolve(fixtureDir, "src/hooks/__tests__"), { recursive: true });
    mkdirSync(localesDir, { recursive: true });

    writeFileSync(
      resolve(fixtureDir, "src/hooks/useExample.ts"),
      'export function useExample() { return t("example.fromTs"); }\n',
    );
    writeFileSync(
      resolve(fixtureDir, "src/hooks/__tests__/useExample.test.ts"),
      'test("mock", () => { const t = (k: string) => k; t("example.testOnly"); });\n',
    );

    for (const locale of ["en", "ja", "ko", "ru", "zh"]) {
      writeFileSync(resolve(localesDir, `${locale}.json`), "{}\n");
    }

    const output = execFileSync(process.execPath, [tsxPath, extractorPath], {
      cwd: fixtureDir,
      encoding: "utf8",
    });

    expect(
      output.match(/➕ Added to en\.json: example\.fromTs/g) ?? [],
    ).toHaveLength(1);
    expect(output).not.toContain("example.testOnly");
  } finally {
    rmSync(fixtureDir, { recursive: true, force: true });
  }
});
