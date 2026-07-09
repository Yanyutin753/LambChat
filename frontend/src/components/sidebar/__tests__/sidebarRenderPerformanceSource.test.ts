import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const sessionItemSource = readFileSync(
  resolve(process.cwd(), "src", "components", "sidebar", "SessionItem.tsx"),
  "utf8",
);

const sessionListSource = readFileSync(
  resolve(
    process.cwd(),
    "src",
    "components",
    "panels",
    "SidebarParts",
    "SessionListContent.tsx",
  ),
  "utf8",
);

test("memoizes session rows so parent sidebar renders do not redraw unchanged items", () => {
  expect(sessionItemSource).toMatch(/export const SessionItem = memo/);
  expect(sessionItemSource).toMatch(/areSessionItemPropsEqual/);
  expect(sessionItemSource).toMatch(/prev\.session === next\.session/);
});

test("memoizes expensive sidebar list derivations", () => {
  expect(sessionListSource).toMatch(/useMemo/);
  expect(sessionListSource).toMatch(/visibleUncategorizedSessions = useMemo/);
  expect(sessionListSource).toMatch(/groupedUncategorized = useMemo/);
  expect(sessionListSource).toMatch(/customProjects = useMemo/);
});
