import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

// 16 线程开发机上 vitest 默认吃满所有核会把桌面拖卡（实测 PSI cpu ~50%），
// 这里钉住 worker 封顶配置不被误删；CI（≤4 核）不受封顶影响。
const source = readFileSync(
  new URL("../../vitest.config.ts", import.meta.url),
  "utf8",
);

test("vitest worker 数不超过可用 CPU 且封顶 8，可通过环境变量覆盖", () => {
  expect(source).toMatch(
    /Number\(process\.env\.VITEST_MAX_WORKERS\)\s*\|\|\s*Math\.min\(8,\s*availableParallelism\(\)\)/,
  );
});

test("maxWorkers 已挂入 defineConfig 的 test 配置块", () => {
  expect(source).toMatch(/^\s{4}maxWorkers,$/m);
});
