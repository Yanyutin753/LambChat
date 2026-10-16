import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";

const src = resolve(import.meta.dirname, "../..");
const css = readFileSync(resolve(src, "styles/icon-scale.css"), "utf8");

function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    if (entry.name === "__tests__") return [];
    const path = resolve(dir, entry.name);
    return entry.isDirectory()
      ? sources(path)
      : /\.tsx$/.test(path)
        ? [path]
        : [];
  });
}

test("all existing numeric icon sizes have a proportional rem fallback", () => {
  const sizes = new Set([12, 16, 24, 32, 40]);
  for (const file of sources(resolve(src, "components"))) {
    for (const match of readFileSync(file, "utf8").matchAll(
      /\bsize=\{(\d+(?:\.\d+)?)\}/g,
    )) {
      // size={1} is the pagination window, not an icon.
      if (Number(match[1]) > 1) sizes.add(Number(match[1]));
    }
  }
  for (const size of sizes) {
    expect(css.replace(/\s+/g, " ")).toContain(
      `[width="${size}"] { --ui-icon-size: ${size / 16}rem; }`,
    );
  }
});

test("icon sizing is a base layer so explicit rem and responsive utilities win", () => {
  expect(css).toMatch(/@layer base\s*\{/);
  expect(css).toMatch(
    /:where\(svg\.lucide\)\s*\{\s*width: var\(--ui-icon-size, 1\.5rem\);\s*height: var\(--ui-icon-size, 1\.5rem\);/,
  );
  expect(css).not.toContain("!important");
  expect(readFileSync(resolve(src, "styles/base.css"), "utf8")).toContain(
    '@import "./icon-scale.css"',
  );
});

test("animated wrappers scale too and let caller size classes override the base", () => {
  expect(css).toMatch(
    /:where\(\.interactive-action-icon > div\)\s*\{\s*width: var\(--interactive-icon-size, 1\.5rem\);\s*height: var\(--interactive-icon-size, 1\.5rem\);/,
  );
  expect(
    readFileSync(
      resolve(
        src,
        "components/layout/DesktopSidebarShell/ActivityRailButton.tsx",
      ),
      "utf8",
    ),
  ).toContain('className="size-[1.1875rem] [&>svg]:size-full"');
});
