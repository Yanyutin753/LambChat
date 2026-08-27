import { readFileSync } from "node:fs";
const tabSource = readFileSync(
  new URL("../ProfilePreferencesTab.tsx", import.meta.url),
  "utf8",
);

test("profile preferences tab wires per-user memory toggle", () => {
  // 状态来自用户 metadata（默认开：!== false 语义）
  expect(tabSource).toMatch(/metadata\?\.memoryEnabled !== false/);
  // 保存走统一的 metadata 合并端点
  expect(tabSource).toMatch(/updateMetadata\(\{ memoryEnabled: next \}\)/);
  // 仅服务器开启记忆功能时展示（enableMemory 门控）
  expect(tabSource).toMatch(/\{enableMemory && \(/);
  // 开关可访问性
  expect(tabSource).toMatch(/role="switch"/);
});
