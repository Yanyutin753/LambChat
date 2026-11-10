import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

test("assistant navigation and chat use the same header height as docked panels", () => {
  const css = readFileSync("src/styles/assistant-workspace.css", "utf8");
  for (const selector of ["header"]) {
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

test("companion navigation separates the sidebar with a theme border", () => {
  const css = readFileSync("src/styles/assistant-workspace.css", "utf8");
  expect(css.match(/\.assistant-workspace-sidebar \{([^}]+)\}/)?.[1]).toContain(
    "border-inline-end: 1px solid var(--theme-border)",
  );
  expect(css.match(/\.assistant-chief \{([^}]+)\}/)?.[1]).toContain(
    "margin: 0.75rem;",
  );
});

test("mobile companion chats keep their title and avoid overlapping global actions", () => {
  const panel = readFileSync(
    "src/components/assistants/AssistantsPanel.tsx",
    "utf8",
  );
  const css = readFileSync("src/styles/assistant-workspace.css", "utf8");
  expect(panel).toContain(
    'data-assistant-selected={assistantId ? "" : undefined}',
  );
  expect(panel).toContain('className="assistant-workspace-title');
  expect(css).toMatch(
    /@media \(max-width: 639px\)[\s\S]*\.chat-header:has\(\[data-assistant-selected\]\) > \.chat-header__actions\s*\{\s*display: none;/,
  );
  expect(css).toMatch(
    /\[data-assistant-selected\]\s+:is\(\s*\.assistant-workspace-brand,\s*\.assistant-workspace-global-action\s*\)\s*\{\s*display: none;/,
  );
});

test("companions use the shared application shell as the only top safe-area owner", () => {
  const shell = readFileSync(
    "src/components/layout/AppContent/AppShell.tsx",
    "utf8",
  );
  const app = readFileSync(
    "src/components/layout/AppContent/index.tsx",
    "utf8",
  );
  const panel = readFileSync(
    "src/components/assistants/AssistantsPanel.tsx",
    "utf8",
  );
  expect(shell).toContain("paddingTop: appSafeAreaTop");
  expect(shell).toContain(
    'activeTab === "assistants" ? setWorkspaceHeaderTarget : undefined',
  );
  expect(app).not.toContain('if (activeTab === "assistants")');
  expect(panel).not.toMatch(/paddingTop:|safe-area-top|safe-area-y/);
});
