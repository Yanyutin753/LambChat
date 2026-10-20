import { existsSync, readFileSync } from "node:fs";
function readSource(relativePath: string): string {
  const url = new URL(relativePath, import.meta.url);
  return existsSync(url) ? readFileSync(url, "utf8") : "";
}

const panelSource = readSource("../../panels/MCPPanel.tsx");
const formSource = readSource("../MCPServerForm.tsx");

test("import dialog dims the json template placeholder", () => {
  // JSON 模板是占位示例，components.css 的 placeholder 色接近正文色，
  // 需加透明度与真实输入拉开视觉层级
  expect(panelSource).toMatch(
    /className="es-textarea font-mono placeholder:opacity-60"/,
  );
});

test("server form dims every example placeholder", () => {
  expect(formSource).toMatch(/placeholder:opacity-60/);
  // 名称、URL、HTTP 头 key/value、每日/每周配额共 6 个输入框，全部弱化，不允许深浅不一
  expect(formSource.match(/placeholder:opacity-60/g)).toHaveLength(6);
  expect(formSource).not.toMatch(/es-input (?!placeholder:opacity-60)/);
});
