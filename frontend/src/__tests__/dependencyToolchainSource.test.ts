import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const packageJson = JSON.parse(
  readFileSync(new URL("../../package.json", import.meta.url), "utf8"),
);

test("build and typecheck use the native TypeScript 7 compiler while ESLint retains the supported compiler API", () => {
  expect(packageJson.devDependencies["typescript-compiler"]).toMatch(/^npm:typescript@~7\./);
  expect(packageJson.devDependencies.typescript).toMatch(/^~6\./);
  for (const command of [packageJson.scripts.build, packageJson.scripts.typecheck]) {
    expect(command).toContain("node node_modules/typescript-compiler/bin/tsc -b");
  }
});


test("Capacitor 8 leaves the existing native insets owner in control", () => {
  const config = readFileSync(new URL("../../capacitor.config.ts", import.meta.url), "utf8");
  expect(config).toContain('SystemBars: { insetsHandling: "disable" }');
  expect(config).not.toContain("bundledWebRuntime");
});
