import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = dirname(fileURLToPath(import.meta.url));

test("usage logs render model display names across desktop, tablet and mobile", () => {
  const source = readFileSync(
    resolve(currentDir, "../UsageLogsTable.tsx"),
    "utf8",
  );

  // 桌面表格、平板行、移动卡三处模型列都走 display name 解析
  expect(
    source.match(/modelDisplayName\(modelLabels/g)?.length,
  ).toBeGreaterThanOrEqual(3);
  // 原始模型 ID 仍可通过悬浮提示查看
  expect(source).toMatch(/title=\{log\.model\}/);
});

test("usage panel maps model value to label for logs and model ranking", () => {
  const source = readFileSync(
    resolve(currentDir, "../../UsagePanel.tsx"),
    "utf8",
  );

  expect(source).toMatch(/buildModelLabelMap\(availableModels\)/);
  expect(source).toMatch(/withModelDisplayNames\(dashboard\.top_models/);
  expect(source).toMatch(/modelLabels=\{modelLabels\}/);
});
