import { readFileSync } from "node:fs";
const source = readFileSync(
  new URL("../SidebarSkeleton.tsx", import.meta.url),
  "utf8",
);

test("sidebar skeleton shares repeated rail and nav row primitives", () => {
  expect(source).toMatch(/function SidebarRailIconSkeleton\(\)/);
  expect(source).toMatch(/function SidebarNavRowSkeleton\(/);
  expect(source).toMatch(/className="skeleton-line size-5 rounded-md"/);
  expect(source).toMatch(
    /className="w-full h-8 rounded-\[10px\] flex items-center gap-3 px-\[9px\]"/,
  );
  expect(source).toMatch(
    /className="skeleton-line size-5 rounded-md shrink-0"/,
  );

  expect(source.match(/skeleton-line size-5 rounded-md"/g)?.length).toBe(1);
  expect(
    source.match(
      /w-full h-8 rounded-\[10px\] flex items-center gap-3 px-\[9px\]/g,
    )?.length,
  ).toBe(1);
  expect(
    source.match(/skeleton-line size-5 rounded-md shrink-0/g)?.length,
  ).toBe(1);
});

test("rail skeleton reserves chat, features and more navigation items", () => {
  expect(source).toMatch(/Array\.from\(\{ length: 8 \},/);
});

test("activity rail hover uses the shared desktop feedback token", () => {
  const css = readFileSync(
    new URL("../../../styles/desktop.css", import.meta.url),
    "utf8",
  );
  expect(css).toMatch(
    /\[data-desktop-activity-rail\]\s+button:not\(:disabled\):hover\s*\{[^}]*background(?:-color)?: var\(--desktop-hover\)/,
  );
});

test("activity rail surface and curved sidebar are shared with the loading shell", () => {
  const css = readFileSync(
    new URL("../../../styles/desktop.css", import.meta.url),
    "utf8",
  )
    .replace(/\s+/g, " ")
    .replace(/\(\s+/g, "(")
    .replace(/\s+\)/g, ")");
  const shell = readFileSync(
    new URL(
      "../../layout/DesktopSidebarShell/DesktopSidebarShell.tsx",
      import.meta.url,
    ),
    "utf8",
  );
  expect(shell).toContain('data-desktop-sidebar-shell={wide ? "" : undefined}');
  expect(source).toContain('data-desktop-sidebar-shell=""');
  expect(source).toContain('import "../../styles/desktop.css"');
  expect(css).toMatch(
    /\[data-desktop-sidebar-shell\] > \[data-desktop-sidebar\]\s*\{[^}]*border-radius: var\(--radius-xl\) 0 0 var\(--radius-xl\)/,
  );
  expect(css).toContain(
    "--desktop-rail-bg: color-mix(in srgb, var(--theme-bg-sidebar) 94%, var(--theme-text))",
  );
});

test("page skeletons reserve the native titlebar and share the workspace header", () => {
  for (const file of ["ChatSkeletons.tsx", "FilesSkeletons.tsx"]) {
    const page = readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
    expect(page).toContain("${appSafeAreaBottom} - var(--titlebar-inset, 0px)");
    expect(page).toContain('data-workspace-content=""');
    expect(page).toContain('className="chat-header ');
  }
});
