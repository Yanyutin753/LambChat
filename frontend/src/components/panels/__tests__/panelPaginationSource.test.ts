import { readFileSync } from "node:fs";
import { expect, test } from "vitest";
const source = (path: string) =>
  readFileSync(new URL(path, import.meta.url), "utf8");
test("marketplace and bookmarks paginate their complete client-side collections", () => {
  for (const file of ["../MarketplacePanel.tsx", "../BookmarksPanel.tsx"]) {
    const code = source(file);
    expect(code).toContain("useClientPagination");
    expect(code).toContain("<Pagination");
    expect(code).toMatch(/slice\((filteredSkills|items)\)\.map/);
  }
});
test("list pagination remains mounted so removing the last page can correct the page", () => {
  for (const file of [
    "../MCPPanel.tsx",
    "../UsersPanel.tsx",
    "../RolesPanel.tsx",
    "../MemoryPanel/index.tsx",
    "../SkillsPanel/SkillsList.tsx",
  ]) {
    expect(source(file)).not.toMatch(/\{total > (pageSize|PAGE_SIZE) &&/);
  }
});
test("team and file panels use explicit page navigation instead of scroll sentinels", () => {
  for (const file of [
    "../../team/TeamBuilderWrapper.tsx",
    "../../fileLibrary/RevealedFilesPanel.tsx",
  ]) {
    const code = source(file);
    expect(code).toContain("<Pagination");
    expect(code).not.toMatch(/loadMoreRef|IntersectionObserver/);
  }
});
test("model configuration and role model assignments share pagination", () => {
  for (const file of [
    "../ModelPanel/tabs/ModelConfigTab.tsx",
    "../ModelPanel/tabs/RolesModelTab.tsx",
  ]) {
    const code = source(file);
    expect(code).toContain("useClientPagination");
    expect(code).toContain("<Pagination");
  }
});
