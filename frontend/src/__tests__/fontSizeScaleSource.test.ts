import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";

function readRepoFile(...segments: string[]): string {
  return readFileSync(
    resolve(import.meta.dirname, "../..", ...segments),
    "utf8",
  );
}

const PX_TEXT_CLASS = /text-\[\d+(?:\.\d+)?px\]/;

function collectSourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    if (entry.isDirectory()) {
      // 测试目录自身的正则字面量不算业务代码
      if (entry.name === "__tests__" || entry.name === "node_modules") {
        return [];
      }
      return collectSourceFiles(resolve(dir, entry.name));
    }
    return /\.(tsx?|jsx?)$/.test(entry.name)
      ? [resolve(dir, entry.name)]
      : [];
  });
}

test("src 不允许写死像素字号：禁止 text-[Npx]，一律用 rem token 刻度", () => {
  const offenders = collectSourceFiles(
    resolve(import.meta.dirname, "../..", "src"),
  ).flatMap((file) =>
    readFileSync(file, "utf8")
      .match(PX_TEXT_CLASS)
      ?.map((match) => `${file}: ${match}`) ?? [],
  );

  expect(
    offenders.slice(0, 10),
    `发现 ${offenders.length} 处像素字号工具类（前 10 条）：\n${offenders.slice(0, 10).join("\n")}`,
  ).toEqual([]);
});

test("tailwind config 定义 rem 字号 token 刻度", () => {
  const config = readRepoFile("tailwind.config.js");

  expect(config).toMatch(/fontSize:\s*\{/);
  // token 只声明 font-size（字符串形式），不附带 line-height，保持与原 text-[Npx] 行为一致
  expect(config).toMatch(/"11":\s*"0\.6875rem"/);
  expect(config).toMatch(/"13":\s*"0\.8125rem"/);
  expect(config).toMatch(/"15":\s*"0\.9375rem"/);
  expect(config).not.toMatch(/fontSize:\s*\{[^}]*px/);
});
