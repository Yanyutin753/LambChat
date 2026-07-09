import { readFileSync } from "node:fs";

function source(path: string) {
  return readFileSync(new URL(path, import.meta.url), "utf8");
}

test("skills search resets pagination in the input change handler before fetching", () => {
  const file = source("../useSkillsActions.ts");

  expect(file).toMatch(/const handleSearchQueryChange = useCallback/);
  expect(file).toMatch(
    /const handleSearchQueryChange = useCallback\(\s*\(query: string\) => \{\s*setPage\(1\);\s*setSearchQuery\(query\);/s,
  );
  expect(file).toMatch(/setSearchQuery:\s*handleSearchQueryChange/);
  expect(file).not.toMatch(
    /useEffect\(\(\) => \{\s*setPage\(1\);\s*\}, \[searchQuery/,
  );
});
