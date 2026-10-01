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

test("memory search replaces the free-text context field and keeps selectable filters", () => {
  expect(filterSource).not.toMatch(/<input/);
  expect(filterSource).not.toMatch(/contextValue|contextOnChange/);
  expect(filterSource).toMatch(/typeOnChange/);
  expect(filterSource).toMatch(/sourceOnChange/);
  expect(panelSource).not.toMatch(/debouncedContext|filterContext/);
  expect(panelSource).toMatch(/search: debouncedSearch \|\| undefined/);
  expect(serviceSource).toMatch(/query\.set\("source", params\.source\)/);
});
