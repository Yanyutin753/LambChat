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
