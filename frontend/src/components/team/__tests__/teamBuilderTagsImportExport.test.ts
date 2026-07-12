import { readFileSync } from "node:fs";
const wrapperSource = readFileSync(
  new URL("../TeamBuilderWrapper.tsx", import.meta.url),
  "utf8",
);
const builderSource = readFileSync(
  new URL("../TeamBuilder.tsx", import.meta.url),
  "utf8",
);

test("team builder list exposes search, tag filter, import, and export controls", () => {
  expect(wrapperSource).toMatch(/searchValue=\{query\}/);
  expect(wrapperSource).toMatch(/searchAccessory=/);
  expect(wrapperSource).toMatch(/PersonaTagFilterDropdown/);
  expect(wrapperSource).toMatch(/handleExport/);
  expect(wrapperSource).toMatch(/handleImportFile/);
  expect(wrapperSource).toMatch(/Download/);
  expect(wrapperSource).toMatch(/Upload/);
});

test("team editor persists team tags", () => {
  expect(builderSource).toMatch(/teamTagsInput/);
  expect(builderSource).toMatch(/inputToTags\(teamTagsInput\)/);
  expect(builderSource).toMatch(/tagsToInput\(team\.tags\)/);
});

test("team editor persists member model overrides", () => {
  expect(builderSource).toMatch(/model_id:\s*null/);
  expect(builderSource).toMatch(/model_id:\s*m\.model_id \?\? null/);
  expect(builderSource).toMatch(/handleModelChange/);
  expect(builderSource).toMatch(/modelApi\s*\.\s*listAvailable\(\)/);
  expect(builderSource).toMatch(/useOptionalSettingsContext/);
  expect(wrapperSource).toMatch(/record\.model_id/);
  expect(wrapperSource).toMatch(
    /model_id:\s*[\s\S]*record\.model_id[\s\S]*:\s*null/,
  );
});

test("team editor persists team sandbox selection and drops member agent modes", () => {
  expect(builderSource).toMatch(/run_in_sandbox:\s*runInSandbox/);
  expect(builderSource).not.toMatch(/agent_id:\s*null/);
  expect(builderSource).not.toMatch(/agent_id:\s*m\.agent_id \?\? null/);
  expect(builderSource).not.toMatch(/handleAgentChange/);
  expect(builderSource).not.toMatch(/agentApi\s*\.\s*list\(\)/);
  expect(wrapperSource).toMatch(/run_in_sandbox:\s*item\.run_in_sandbox === true/);
  expect(wrapperSource).not.toMatch(/agent_id:\s*null/);
  expect(wrapperSource).toMatch(/"agent_id" in record/);
  expect(wrapperSource).toMatch(/legacyMemberAgentIdCount/);
});
