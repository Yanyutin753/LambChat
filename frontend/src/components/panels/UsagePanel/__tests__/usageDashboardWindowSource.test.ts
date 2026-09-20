import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = dirname(fileURLToPath(import.meta.url));

test("dashboard fetch uses the same local date window as the logs fetch", () => {
  const source = readFileSync(
    resolve(currentDir, "../../UsagePanel.tsx"),
    "utf8",
  );

  // 控制台两半数据（KPI 来自 /logs、看板来自 /dashboard）必须落在同一时间窗：
  // fetchDashboard 复用 computeDateRange 的本地 0 点 start_date，而不是各算各的
  const dashboardCall = source.match(
    /usageApi\.getDashboard\(\{[\s\S]*?\}\)/,
  )?.[0];
  expect(dashboardCall).toBeDefined();
  expect(dashboardCall).toMatch(/\.\.\.dateRange/);
  expect(
    source.match(/computeDateRange\(period\)/g)?.length,
  ).toBeGreaterThanOrEqual(2);
});

test("usage panel defaults to week so the dashboard aggregate hits the started_at index", () => {
  const source = readFileSync(
    resolve(currentDir, "../../UsagePanel.tsx"),
    "utf8",
  );

  // 默认 all 会让后端 $match 为空，usage_logs 的 6 个 started_at 索引全部失效，
  // 变成每次打开面板全表扫描（COLLSCAN 1w+ 文档、140-160ms，随数据量线性变差）。
  // 默认 week 后 $match 走 started_at_-1 索引；"全部"仍是用户可选项。
  expect(source).toMatch(/useState<string>\("week"\)/);
});
