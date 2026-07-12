import { readFileSync } from "node:fs";
import { join } from "node:path";

const usagePanelSource = readFileSync(
  join(import.meta.dirname, "../UsagePanel.tsx"),
  "utf8",
);

const usageTableSource = readFileSync(
  join(import.meta.dirname, "../UsagePanel/UsageLogsTable.tsx"),
  "utf8",
);

const insightSource = readFileSync(
  join(import.meta.dirname, "../UsagePanel/InsightStrip.tsx"),
  "utf8",
);

const trendSource = readFileSync(
  join(import.meta.dirname, "../UsagePanel/MiniTrend.tsx"),
  "utf8",
);

test("usage admin and read views present different dashboard context", () => {
  expect(usagePanelSource).toMatch(/const dashboardTitle = isAdmin/);
  expect(usagePanelSource).toMatch(/usage\.dashboard\.titleAdmin/);
  expect(usagePanelSource).toMatch(/usage\.dashboard\.titleUser/);
  expect(usagePanelSource).toMatch(
    /isAdmin && \(\s*<RankingList[\s\S]*?usage\.ranking\.userAdmin/,
  );
  expect(usagePanelSource).toMatch(
    /isAdmin && dashboard && dashboard\.triggers\.length > 0/,
  );
});

test("usage table keeps admin-only user column and aligned numeric columns", () => {
  expect(usageTableSource).toMatch(/gridTemplateColumns: desktopGridTemplate/);
  expect(usageTableSource).toMatch(/desktopGridTemplate = isAdmin/);
  expect(usageTableSource).toMatch(/min-w-\[1080px\]/);
  expect(usageTableSource).toMatch(/minmax\(8rem,\.7fr\)|minmax\(9rem,\.8fr\)/);
  expect(usageTableSource).toMatch(/usage\.roleOrTeam/);
  expect(usageTableSource).toMatch(/personaOrTeam/);
  expect(usageTableSource).toMatch(/usage\.cache/);
  expect(usageTableSource).toMatch(/usage\.cacheRead/);
  expect(usageTableSource).toMatch(/text-right/);
  expect(usageTableSource).toMatch(/fmt\(log\.cache_read_tokens\)/);
  expect(usageTableSource).not.toMatch(/opacity-15/);
  expect(usageTableSource).not.toMatch(/<table/);
  expect(usageTableSource).not.toMatch(
    /grid-cols-3 gap-1\.5 rounded-lg bg-\[var\(--usage-inset-bg\)\]/,
  );
});

test("usage visual accents use theme colors instead of hard-coded chart palette", () => {
  expect(insightSource).not.toMatch(/border-l-(blue|violet|cyan|rose)-500/);
  expect(insightSource).not.toMatch(
    /border-l-\[3px\]|border-l-\[var\(--theme-primary\)\]/,
  );
  expect(trendSource).not.toMatch(/#3b82f6|#06b6d4|bg-blue-500/);
  expect(trendSource).toMatch(/var\(--theme-primary\)/);
  expect(trendSource).toMatch(/var\(--usage-chart-secondary\)/);
});
