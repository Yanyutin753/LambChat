import { readFileSync } from "node:fs";

function source(path: string) {
  return readFileSync(new URL(path, import.meta.url), "utf8");
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

test("remote paginated panel searches reset pagination in their change handlers", () => {
  const cases = [
    {
      path: "../../panels/MCPPanel.tsx",
      handler: "handleSearchQueryChange",
      reset: "setPage(1);",
      value: "setSearchQuery(query);",
      prop: /onSearchChange=\{handleSearchQueryChange\}/,
      staleEffect:
        /useEffect\(\(\) => \{\s*setPage\(1\);\s*\}, \[searchQuery\]\);/,
    },
    {
      path: "../../panels/RolesPanel.tsx",
      handler: "handleSearchQueryChange",
      reset: "setPage(1);",
      value: "setSearchQuery(query);",
      prop: /onSearchChange=\{handleSearchQueryChange\}/,
      staleEffect:
        /useEffect\(\(\) => \{\s*setPage\(1\);\s*\}, \[searchQuery\]\);/,
    },
    {
      path: "../../panels/UsersPanel.tsx",
      handler: "handleSearchQueryChange",
      reset: "setPage(1);",
      value: "setSearchQuery(query);",
      prop: /onSearchChange=\{handleSearchQueryChange\}/,
      staleEffect:
        /useEffect\(\(\) => \{\s*setPage\(1\);\s*\}, \[debouncedSearch\]\);/,
    },
    {
      path: "../../panels/UsagePanel.tsx",
      handler: "handleSearchQueryChange",
      reset: "setSkip(0);",
      value: "setSearchQuery(query);",
      prop: /onSearchChange=\{isAdmin \? handleSearchQueryChange : undefined\}/,
      staleEffect:
        /useEffect\(\(\) => \{\s*setSkip\(0\);\s*\}, \[period, debouncedSearch\]\);/,
    },
    {
      path: "../../panels/MemoryPanel/index.tsx",
      handler: "handleSearchQueryChange",
      reset: "setPage(1);",
      value: "setSearchQuery(query);",
      prop: /onSearchChange=\{handleSearchQueryChange\}/,
      staleEffect:
        /useEffect\(\(\) => \{\s*setPage\(1\);\s*\}, \[filterType, filterSource, debouncedSearch\]\);/,
    },
    {
      path: "../../persona/usePersonaPlaza.ts",
      handler: "handleQueryChange",
      reset: "setPage(1);",
      value: "setQuery(nextQuery);",
      prop: /setQuery: handleQueryChange/,
      staleEffect:
        /useEffect\(\(\) => \{\s*setPage\(1\);\s*\}, \[query, activeTag, scopeFilter\]\);/,
    },
    {
      path: "../../persona/PersonaEditorSkillSelector.tsx",
      handler: "handleSkillSearchChange",
      reset: "setSkillPage(1);",
      value: "setSkillSearch(query);",
      prop: /onValueChange=\{handleSkillSearchChange\}/,
      staleEffect:
        /onChange=\{\(e\) => handleSkillSearchChange\(e\.target\.value\)\}/,
    },
  ];

  for (const item of cases) {
    const file = source(item.path);
    expect(file).toMatch(new RegExp(`const ${item.handler} = useCallback`));
    expect(file).toMatch(
      new RegExp(`${escapeRegExp(item.reset)}\\s*${escapeRegExp(item.value)}`),
    );
    expect(file).toMatch(item.prop);
    expect(file).not.toMatch(item.staleEffect);
  }
});
