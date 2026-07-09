import type { Project } from "../../../../types";
import { isSidebarProject } from "../projectFilters.ts";

function project(type: Project["type"]): Project {
  return {
    id: `${type}-project`,
    user_id: "user-1",
    name: type,
    type,
    icon: "💬",
    sort_order: 100,
    created_at: "2026-05-09T00:00:00.000Z",
    updated_at: "2026-05-09T00:00:00.000Z",
  };
}

test("sidebar includes channel projects", () => {
  expect(isSidebarProject(project("channel"))).toBe(true);
});

test("sidebar keeps favorites in the dedicated favorites slot", () => {
  expect(isSidebarProject(project("favorites"))).toBe(false);
});
