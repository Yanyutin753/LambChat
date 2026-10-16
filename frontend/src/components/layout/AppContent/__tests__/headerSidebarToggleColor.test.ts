import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../Header.tsx", import.meta.url), "utf8");

test("mobile sidebar expand toggle matches the sidebar collapse icon color", () => {
  expect(source).toMatch(
    /className="chat-header__sidebar-expand flex h-8 w-8 items-center justify-center rounded-lg text-theme-text-secondary hover:bg-theme-bg-hover hover:text-theme-text sm:hidden transition-colors"/,
  );
  expect(source).toMatch(
    /<SidebarToggleIcon\s+className="size-4 max-sm:dark:text-stone-300"\s*\/>/,
  );
  expect(source).toContain("<MoreHorizontal size={16} />");
});

test("header overflow menu trigger uses theme colors and visible interaction states", () => {
  expect(source).toMatch(
    /className="flex size-11 sm:size-8 items-center justify-center rounded-lg text-theme-text-secondary hover:bg-theme-bg-hover aria-expanded:bg-theme-bg-subtle aria-expanded:text-theme-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-\[var\(--theme-ring\)\]"\s+title=\{t\("common\.menu"\)\}/,
  );
});
