import { createPagedGroups } from "../shared/selectorPagination.ts";

test("createPagedGroups paginates after applying stable grouped order", () => {
  const result = createPagedGroups(
    [
      { name: "zeta", category: "mcp" },
      { name: "bravo", category: "builtin" },
      { name: "alpha", category: "mcp" },
    ],
    {
      page: 1,
      pageSize: 2,
      getGroupKey: (item) => item.category,
      sortItems: (a, b) => a.name.localeCompare(b.name),
    },
  );

  expect(Object.keys(result.fullGroups)).toEqual(["mcp", "builtin"]);
  expect(
    Object.values(result.pagedGroups)
      .flat()
      .map((item) => item.name),
  ).toEqual(["alpha", "zeta"]);
  expect(result.totalPages).toBe(2);
});
