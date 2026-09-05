import { readFileSync } from "node:fs";

test("collapsible section header does not nest action buttons inside the toggle", () => {
  const componentSource = readFileSync(
    new URL("../CollapsibleSection.tsx", import.meta.url),
    "utf8",
  );
  const componentsCss = readFileSync(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  expect(componentSource).not.toMatch(
    /<button[\s\S]*?\{action && <span onClick=\{\(e\) => e\.stopPropagation\(\)\}>\{action\}<\/span>\}[\s\S]*?<\/button>/,
  );
  expect(componentSource).toMatch(
    /<button[\s\S]*?aria-expanded=\{expanded\}[\s\S]*?onClick=\{toggleExpanded\}/,
  );
  expect(componentSource).toMatch(
    /\{action && <div className="shrink-0">\{action\}<\/div>\}/,
  );
  expect(componentSource).toMatch(
    /"collapsible-section-card--default bg-theme-bg-card border border-theme-border shadow-sm"/,
  );
  expect(componentSource).not.toMatch(/:\s*"bg-theme-bg-subtle"/);
  expect(componentsCss).toMatch(
    /\.collapsible-section-card--default\s*\{[\s\S]*?background:\s*var\(--theme-bg-card\);[\s\S]*?box-shadow:/,
  );
});

test("expanded collapsible section cards fill the available panel height", () => {
  const sectionSource = readFileSync(
    new URL("../CollapsibleSection.tsx", import.meta.url),
    "utf8",
  );
  const panelSource = readFileSync(
    new URL("../SubagentPanelContent.tsx", import.meta.url),
    "utf8",
  );

  expect(panelSource).toMatch(
    /className="flex min-h-0 flex-1 flex-col space-y-3"/,
  );
  expect(sectionSource).toMatch(
    /<div\s+data-sidebar-snapshot-key=\{`\$\{sectionKey\}-content`\}\s+className="mt-2 flex-1 min-h-0 overflow-y-auto animate-\[fade-in_150ms_ease-out\]"\s*>/,
  );
  expect(sectionSource).toMatch(/expanded && expandedClassName/);
  expect(panelSource).toMatch(
    /title=\{t\("chat\.message\.result"\)\}[\s\S]*?expandedClassName="flex min-h-0 flex-col grow shrink-0"/,
  );
});

test("generic tool call panel stretches the result card to fill remaining height", () => {
  const toolCallItemSource = readFileSync(
    new URL("../ToolCallItem.tsx", import.meta.url),
    "utf8",
  );

  // 面板根节点：占满 panel-body 并自身兜底滚动
  expect(toolCallItemSource).toMatch(
    /className="relative flex h-full min-h-0 flex-col overflow-y-auto p-2 sm:p-4 \[&_pre\]:!text-sm \[&_pre\]:!max-h-none"/,
  );
  // 内层 flex 列承载小节，result 卡片展开时吃掉剩余空间
  expect(toolCallItemSource).toMatch(
    /className="flex min-h-0 flex-1 flex-col space-y-3"/,
  );
  expect(toolCallItemSource).toMatch(
    /title=\{t\("chat\.message\.result"\)\}[\s\S]*?expandedClassName="flex min-h-0 flex-col grow shrink-0"/,
  );
});

test("tool live panel details fill the panel height while inline previews keep their caps", () => {
  const itemsDir = new URL("../items/", import.meta.url);
  const panelDetailItems = [
    "ToolSearchItem",
    "TransferItem",
    "UploadUrlToSandboxItem",
    "SkillSearchItem",
    "ConversationHistoryItem",
  ];

  for (const item of panelDetailItems) {
    const source = readFileSync(new URL(`${item}.tsx`, itemsDir), "utf8");
    // 面板详情根节点铺满 panel-body，自身兜底滚动
    expect(
      source,
      `${item} panel detail root should fill the panel height`,
    ).toMatch(
      /className="flex h-full min-h-0 flex-col space-y-3 overflow-y-auto p-2 sm:p-4 \[&_pre\]:!max-h-none"/,
    );
    expect(
      source,
      `${item} should not keep the old shrink-to-fit panel detail root`,
    ).not.toMatch(/space-y-3 max-h-full overflow-y-auto p-2 sm:p-4/);
  }

  // 结果区直接可滚动的三个面板：result 区块伸展吃掉剩余空间
  for (const item of [
    "ToolSearchItem",
    "TransferItem",
    "UploadUrlToSandboxItem",
  ]) {
    const source = readFileSync(new URL(`${item}.tsx`, itemsDir), "utf8");
    expect(
      source,
      `${item} panel result block should stretch to fill remaining height`,
    ).toMatch(
      /group\/result relative flex-1 min-h-0 text-xs text-theme-text-secondary overflow-y-auto min-w-0/,
    );
  }
});
