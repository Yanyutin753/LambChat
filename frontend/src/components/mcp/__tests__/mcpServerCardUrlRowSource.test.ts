import { existsSync, readFileSync } from "node:fs";
function readSource(relativePath: string): string {
  const url = new URL(relativePath, import.meta.url);
  return existsSync(url) ? readFileSync(url, "utf8") : "";
}

const cardSource = readSource("../MCPServerCard.tsx");

test("url row renders only when the server has a url", () => {
  // 内置/无 URL 的服务器不应渲染空行,否则卡片内容区留白不均
  expect(cardSource).toMatch(/\{server\.url && \(/);
  expect(cardSource).not.toMatch(/\{server\.url \|\| ""\}/);
});
