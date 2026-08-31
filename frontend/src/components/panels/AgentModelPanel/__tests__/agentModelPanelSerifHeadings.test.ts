import { readFileSync } from "node:fs";

/**
 * Agent + Model 面板的大字号文字（分段切换器、列表项名称、表头行）
 * 必须与其他 panel 一致使用 font-serif。
 */
const panelSource = readFileSync(
  new URL("../AgentModelPanel.tsx", import.meta.url),
  "utf8",
);
const agentSectionSource = readFileSync(
  new URL("../AgentSection.tsx", import.meta.url),
  "utf8",
);
const modelSectionSource = readFileSync(
  new URL("../ModelSection.tsx", import.meta.url),
  "utf8",
);
const globalAgentTabSource = readFileSync(
  new URL("../../AgentPanel/tabs/GlobalAgentTab.tsx", import.meta.url),
  "utf8",
);
const rolesAgentTabSource = readFileSync(
  new URL("../../AgentPanel/tabs/RolesAgentTab.tsx", import.meta.url),
  "utf8",
);
const rolesModelTabSource = readFileSync(
  new URL("../../ModelPanel/tabs/RolesModelTab.tsx", import.meta.url),
  "utf8",
);
const modelConfigTabSource = readFileSync(
  new URL("../../ModelPanel/tabs/ModelConfigTab.tsx", import.meta.url),
  "utf8",
);

test("section and tab switchers use font-serif like other panel tabs", () => {
  expect(panelSource).toMatch(/agent-model-section-switcher[^"]*font-serif/);
  expect(agentSectionSource).toMatch(/inline-grid grid-cols-2[^"]*font-serif/);
  expect(modelSectionSource).toMatch(/inline-grid grid-cols-2[^"]*font-serif/);
});

test("agent list item names use font-serif", () => {
  expect(globalAgentTabSource).toMatch(/gap-3 font-serif px-4 py-3\.5/);
  expect(agentSectionSource).toMatch(
    /<h4 className="truncate text-sm font-medium font-serif/,
  );
  expect(rolesAgentTabSource).toMatch(
    /<div className="truncate text-sm font-medium font-serif/,
  );
});

test("model list item names use font-serif", () => {
  expect(rolesModelTabSource).toMatch(
    /<div className="truncate text-sm font-medium font-serif/,
  );
  expect(modelConfigTabSource).toMatch(
    /<h4 className="text-sm font-semibold font-serif/,
  );
});

test("roles agent tab section header row uses font-serif like roles model tab", () => {
  expect(rolesModelTabSource).toMatch(/justify-between gap-3 font-serif/);
  expect(rolesAgentTabSource).toMatch(/glass-bg-subtle\)\] px-4 py-2\.5 font-serif/);
});
