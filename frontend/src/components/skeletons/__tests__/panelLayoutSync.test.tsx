/** @vitest-environment jsdom */
import { render, cleanup } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { afterEach, expect, test } from "vitest";
import { PanelHeaderSkeleton } from "../PanelHeaderSkeleton";
import {
  SkillsPanelSkeleton,
  MarketplacePanelSkeleton,
  UsersPanelSkeleton,
  RolesPanelSkeleton,
  MCPPanelSkeleton,
  ScheduledTaskPanelSkeleton,
  TaskSessionListSkeleton,
  MemoryPanelSkeleton,
} from "../PanelSkeletons";
import {
  BookmarksPanelSkeleton,
  NotificationsPanelSkeleton,
  TeamPanelSkeleton,
} from "../ResourceSkeletons";
import { FilesContentSkeleton } from "../FilesSkeletons";
import { PersonaPlazaSkeleton } from "../PersonaSkeletons";

afterEach(cleanup);

test.each(
  [
    SkillsPanelSkeleton,
    MarketplacePanelSkeleton,
    UsersPanelSkeleton,
    RolesPanelSkeleton,
    MCPPanelSkeleton,
    ScheduledTaskPanelSkeleton,
    TaskSessionListSkeleton,
    MemoryPanelSkeleton,
    PersonaPlazaSkeleton,
    BookmarksPanelSkeleton,
    NotificationsPanelSkeleton,
    TeamPanelSkeleton,
    FilesContentSkeleton,
  ].map((Component) => [Component.name, Component] as const),
)("%s keeps pagination outside its scrolling body", (_name, Component) => {
  const { container } = render(<Component />);
  const body = container.querySelector(".panel-body.overflow-y-auto");
  const footer = container.querySelector(".panel-pagination");
  expect(body).not.toBeNull();
  expect(footer).not.toBeNull();
  expect(body?.contains(footer)).toBe(false);
  expect(body?.parentElement).toBe(footer?.parentElement);
});

test("search header has one inline mobile menu and the current identity spacing", () => {
  const { container } = render(<PanelHeaderSkeleton />);
  expect(
    container.querySelectorAll(".panel-header__mobile-actions"),
  ).toHaveLength(1);
  expect(
    container.querySelector(
      ".panel-header__search-box .panel-header__mobile-actions",
    ),
  ).not.toBeNull();
  expect(container.querySelector(".panel-header__illustration")).not.toBeNull();
  expect(
    container.querySelector(".panel-header__search-row")?.className,
  ).toContain("mt-2");
});

test("header without search does not reserve search padding", () => {
  const { container } = render(<PanelHeaderSkeleton hasSearch={false} />);
  expect(container.querySelector(".panel-header--has-search")).toBeNull();
});

test("every management route has a page-specific lazy loading skeleton", () => {
  const source = readFileSync(
    "src/components/layout/AppContent/TabContent.tsx",
    "utf8",
  );
  for (const route of [
    "settings",
    "files",
    "bookmarks",
    "persona",
    "team",
    "notifications",
    "memory",
  ]) {
    expect(source).toMatch(new RegExp(`${route}: <\\w+Skeleton`));
  }
});

test.each(
  [
    ScheduledTaskPanelSkeleton,
    NotificationsPanelSkeleton,
    FilesContentSkeleton,
  ].map((Component) => [Component.name, Component] as const),
)("%s reserves the page description", (_name, Component) => {
  const { container } = render(<Component />);
  expect(container.querySelector(".panel-header__subtitle")).not.toBeNull();
  expect(container.querySelector(".panel-header__title")).not.toBeNull();
});

test("users skeleton switches table and cards at the same panel width as the loaded page", () => {
  const { container } = render(<UsersPanelSkeleton />);
  expect(container.querySelector(".panel-table-view")).not.toBeNull();
  expect(container.querySelector(".panel-list-view")).not.toBeNull();
});

test("persona route fallback fills its flex container", async () => {
  const { PersonaPageSkeleton } = await import("../PersonaSkeletons");
  const { container } = render(<PersonaPageSkeleton />);
  expect(container.firstElementChild?.classList.contains("w-full")).toBe(true);
  expect(
    container.firstElementChild?.firstElementChild?.classList.contains(
      "flex-1",
    ),
  ).toBe(true);
});

test("feedback route fallback keeps filters in the header instead of a separate row", async () => {
  const { FeedbackPanelSkeleton } = await import("../InfraSkeletons");
  const { container } = render(<FeedbackPanelSkeleton />);
  expect(
    container.querySelector(".panel-header--section-switch"),
  ).not.toBeNull();
  expect(container.querySelector(".panel-inset.flex")).toBeNull();
});

test("skills hub fallback keeps its switcher inside the current page header", async () => {
  const { SkillsHubSkeleton } = await import("../SkillSkeletons");
  const { container } = render(<SkillsHubSkeleton />);
  expect(
    container.querySelector(".panel-header--section-switch .skills-hub-tabs"),
  ).not.toBeNull();
});

test("agent model fallback reserves the section switcher in its header", async () => {
  const { AgentModelPanelSkeleton } = await import("../SettingsSkeletons");
  const { container } = render(<AgentModelPanelSkeleton />);
  expect(
    container.querySelector(
      ".panel-header--agent-model .agent-model-section-switcher",
    ),
  ).not.toBeNull();
});

test("files fallback uses the same flexible search lane as the toolbar", () => {
  const { container } = render(<FilesContentSkeleton />);
  expect(
    container.querySelector(".file-library-toolbar__search-group"),
  ).not.toBeNull();
  expect(
    container.querySelector(".file-library-toolbar__search"),
  ).not.toBeNull();
});

test.each([SkillsPanelSkeleton, PersonaPlazaSkeleton])(
  "%s uses current shared card banner geometry",
  (Component) => {
    const { container } = render(<Component />);
    expect(container.querySelectorAll(".scb__banner")).toHaveLength(24);
  },
);
