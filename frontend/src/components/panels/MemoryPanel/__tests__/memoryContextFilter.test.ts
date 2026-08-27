import { readFileSync } from "node:fs";
const filterSource = readFileSync(
  new URL("../MemoryFilter.tsx", import.meta.url),
  "utf8",
);
const panelSource = readFileSync(
  new URL("../index.tsx", import.meta.url),
  "utf8",
);
const serviceSource = readFileSync(
  new URL("../../../../services/api/memory.ts", import.meta.url),
  "utf8",
);

test("memory panel wires context scope filter end to end", () => {
  // 过滤器渲染 context 输入并回传变更
  expect(filterSource).toMatch(/contextValue/);
  expect(filterSource).toMatch(/contextOnChange/);
  expect(filterSource).toMatch(/memory\.contextFilterPlaceholder/);
  // 面板持有状态、防抖后并入列表请求
  expect(panelSource).toMatch(/filterContext, setFilterContext/);
  expect(panelSource).toMatch(/setDebouncedContext/);
  expect(panelSource).toMatch(/context: debouncedContext \|\| undefined/);
  // service 层透传 context 查询参数
  expect(serviceSource).toMatch(/context\?: string/);
  expect(serviceSource).toMatch(/query\.set\("context", params\.context\)/);
});
