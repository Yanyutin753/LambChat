import { readFileSync } from "node:fs";
const source = readFileSync(
  new URL("../BatchCreateModal.tsx", import.meta.url),
  "utf8",
);

test("batch create delegates payload building to the shared pure helpers", () => {
  expect(source).toMatch(/buildModelCreateFromRow/);
  expect(source).toMatch(/normalizeImportedModels/);
  expect(source).toMatch(/mergeSharedIntoImported/);
});

test("batch rows support the latest model config structure", () => {
  expect(source).toMatch(/<ModelIconSelect/);
  expect(source).toMatch(/row\.priceInput/);
  expect(source).toMatch(/checked=\{row\.supportsVision\}/);
  expect(source).toMatch(/checked=\{row\.imageUrlToBase64\}/);
  // 行级 API 凭据可覆盖共享配置
  expect(source).toMatch(/row\.apiKey/);
  expect(source).toMatch(/row\.apiBase/);
});

test("shared connection config covers request headers for both tabs", () => {
  expect(source).toMatch(/batchRequestHeaders/);
  expect(source).toMatch(/parseRequestHeadersInput/);
});

test("json import tab uploads model config files", () => {
  expect(source).toMatch(/type="file"/);
  expect(source).toMatch(/accept="\.json/);
  expect(source).toMatch(/onDrop=/);
});

test("import success closes via callback instead of a delayed timer", () => {
  expect(source).not.toMatch(/setTimeout/);
});
