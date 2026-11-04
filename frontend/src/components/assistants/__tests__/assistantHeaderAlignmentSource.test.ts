import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

test("assistant navigation and chat use the same header height as docked panels", () => {
  const css = readFileSync("src/styles/assistant-workspace.css", "utf8");
  for (const selector of ["sidebar-top", "header"]) {
    const rule = css.match(
      new RegExp(`\\.assistant-workspace-${selector} \\{([^}]+)\\}`),
    )?.[1];
    expect(rule).toContain("height: var(--workspace-header-height, 3rem)");
    expect(rule).not.toContain("min-height: 4.25rem");
  }
  expect(css).not.toMatch(
    /\.assistant-workspace-header\s*\{[^}]*min-height: 3\.5rem/,
  );
});

test("assistant pages reuse the chat header frame and theme background", () => {
  const panel = readFileSync(
    "src/components/assistants/AssistantsPanel.tsx",
    "utf8",
  );
  const header = readFileSync(
    "src/components/layout/AppContent/Header.tsx",
    "utf8",
  );
  const css = readFileSync("src/styles/assistant-workspace.css", "utf8");
  expect(panel).toContain(
    '<ChatHeaderFrame className="assistant-workspace-header">',
  );
  expect(header).toContain("<ChatHeaderFrame>");
  expect(css.match(/\.assistant-workspace-main \{([^}]+)\}/)?.[1]).toContain(
    "background: var(--theme-bg)",
  );
  expect(
    readFileSync("src/components/assistants/AssistantTasksDialog.tsx", "utf8"),
  ).toContain("<PanelHeader");
});
