/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../../i18n";
import { Permission } from "../../../../types";
import { SkillsPanel } from "..";

let permissions: Permission[] = [];
const fetchMock = vi.fn<typeof fetch>();
vi.mock("../../../../hooks/useAuth", () => ({
  useAuth: () => ({
    user: { id: "reader" },
    hasAnyPermission: (values: Permission[]) =>
      values.some((value) => permissions.includes(value)),
  }),
}));
vi.mock("../../../../contexts/SettingsContext", () => ({
  useSettingsContext: () => ({ enableSkills: true }),
}));
beforeEach(async () => {
  await i18n.changeLanguage("zh");
  permissions = [Permission.SKILL_READ];
  vi.stubGlobal("matchMedia", () => ({
    matches: false,
    addListener() {},
    removeListener() {},
  }));
  fetchMock.mockReset();
  fetchMock.mockImplementation(
    async () =>
      new Response(
        JSON.stringify({
          skills: [
            {
              skill_name: "alpha",
              enabled: true,
              description: "Research notes",
              tags: ["Research"],
              files: ["SKILL.md"],
              file_count: 1,
              installed_from: "manual",
              is_published: false,
            },
          ],
          total: 1,
          available_tags: ["Research"],
        }),
      ),
  );
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function openCard() {
  const result = render(
    <MemoryRouter>
      <SkillsPanel embedded />
    </MemoryRouter>,
  );
  const card = await screen.findByRole("group", { name: "alpha" });
  fireEvent.click(
    within(card).getByRole("button", { name: i18n.t("common.moreOptions") }),
  );
  return { card, ...result };
}
function menuActions() {
  return screen.getAllByRole("menuitem").map((el) => el.textContent);
}

test("read access retains preference/export/filter controls and removes all mutation entry points", async () => {
  const { card } = await openCard();
  expect(menuActions()).toEqual([
    i18n.t("personaPresets.pin"),
    i18n.t("personaPresets.favorite"),
    i18n.t("skills.exportZip"),
  ]);
  expect(within(card).queryByRole("checkbox")).toBeNull();
  expect(
    within(card).queryByRole("button", { name: i18n.t("skills.card.disable") }),
  ).toBeNull();
  for (const key of [
    "common.selectAll",
    "skills.github",
    "skills.uploadZip",
    "skills.newSkill",
  ])
    expect(
      screen.queryAllByRole("button", { name: i18n.t(key), exact: true }),
    ).toHaveLength(0);
  expect(
    screen.getByPlaceholderText(i18n.t("skills.searchPlaceholder")),
  ).toBeEnabled();
  expect(
    screen.getByRole("button", { name: i18n.t("skills.filter"), exact: true }),
  ).toBeEnabled();
});

test("write access enables creation/edit/toggle and batch toggle without granting delete", async () => {
  permissions.push(Permission.SKILL_WRITE);
  const { card } = await openCard();
  expect(menuActions()).toContain(i18n.t("skills.card.edit"));
  expect(menuActions()).not.toContain(i18n.t("skills.card.delete"));
  fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
  expect(
    screen.getAllByRole("button", {
      name: i18n.t("skills.newSkill"),
      exact: true,
    }).length,
  ).toBeGreaterThan(0);
  fireEvent.click(within(card).getByRole("checkbox"));
  const bar = screen.getByRole("group", {
    name: new RegExp(i18n.t("skills.batchSelected")),
  });
  expect(
    within(bar).getByRole("button", {
      name: i18n.t("skills.card.enable"),
      exact: true,
    }),
  ).toBeEnabled();
  expect(
    within(bar).queryByRole("button", {
      name: i18n.t("common.delete"),
      exact: true,
    }),
  ).toBeNull();
});

test("delete access enables card/batch deletion without exposing write-only operations", async () => {
  permissions.push(Permission.SKILL_DELETE);
  const { card } = await openCard();
  expect(menuActions()).toContain(i18n.t("skills.card.delete"));
  expect(menuActions()).not.toContain(i18n.t("skills.card.edit"));
  expect(menuActions()).not.toContain(i18n.t("skills.card.disable"));
  fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
  fireEvent.click(within(card).getByRole("checkbox"));
  const bar = screen.getByRole("group", {
    name: new RegExp(i18n.t("skills.batchSelected")),
  });
  expect(
    within(bar).getByRole("button", {
      name: i18n.t("common.delete"),
      exact: true,
    }),
  ).toBeEnabled();
  expect(
    within(bar).queryByRole("button", {
      name: i18n.t("skills.card.enable"),
      exact: true,
    }),
  ).toBeNull();
  expect(
    screen.queryAllByRole("button", {
      name: i18n.t("skills.newSkill"),
      exact: true,
    }),
  ).toHaveLength(0);
});

test("publish permission stays independent from editing and deletion", async () => {
  permissions.push(Permission.MARKETPLACE_PUBLISH);
  await openCard();
  expect(menuActions()).toContain(i18n.t("skills.card.publishToMarketplace"));
  expect(menuActions()).not.toContain(i18n.t("skills.card.edit"));
  expect(menuActions()).not.toContain(i18n.t("skills.card.delete"));
});

test("revoking write/delete permissions removes stale selection and batch controls", async () => {
  permissions.push(Permission.SKILL_WRITE, Permission.SKILL_DELETE);
  const { card, rerender } = await openCard();
  fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
  await userEvent.click(within(card).getByRole("checkbox"));
  expect(within(card).getByRole("checkbox")).toHaveFocus();
  permissions = [Permission.SKILL_READ];
  rerender(
    <MemoryRouter>
      <SkillsPanel embedded />
    </MemoryRouter>,
  );
  await waitFor(() =>
    expect(
      screen.queryByRole("group", {
        name: new RegExp(i18n.t("skills.batchSelected")),
      }),
    ).toBeNull(),
  );
  expect(screen.queryByRole("checkbox")).toBeNull();
  expect(card).toHaveFocus();
  expect(
    fetchMock.mock.calls.every(
      ([, options]) => !options?.method || options.method === "GET",
    ),
  ).toBe(true);
  permissions.push(Permission.SKILL_WRITE);
  rerender(
    <MemoryRouter>
      <SkillsPanel embedded />
    </MemoryRouter>,
  );
  expect(screen.getByRole("checkbox")).not.toBeChecked();
});

test("a failed write retry disappears when only delete permission remains", async () => {
  permissions.push(Permission.SKILL_WRITE, Permission.SKILL_DELETE);
  const { card, rerender } = await openCard();
  fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
  fireEvent.click(within(card).getByRole("checkbox"));
  fetchMock.mockResolvedValueOnce(
    new Response(JSON.stringify({ detail: { message: "Unavailable" } }), {
      status: 503,
    }),
  );
  const bar = screen.getByRole("group", {
    name: new RegExp(i18n.t("skills.batchSelected")),
  });
  fireEvent.click(
    within(bar).getByRole("button", {
      name: i18n.t("skills.card.enable"),
      exact: true,
    }),
  );
  expect(
    await screen.findByRole("button", {
      name: i18n.t("common.retry"),
      exact: true,
    }),
  ).toBeEnabled();
  await userEvent.tab();
  expect(
    screen.getByRole("button", { name: i18n.t("common.retry"), exact: true }),
  ).toHaveFocus();
  permissions = [Permission.SKILL_READ, Permission.SKILL_DELETE];
  rerender(
    <MemoryRouter>
      <SkillsPanel embedded />
    </MemoryRouter>,
  );
  expect(
    screen.queryByRole("button", { name: i18n.t("common.retry"), exact: true }),
  ).toBeNull();
  expect(
    within(bar).getByRole("button", {
      name: i18n.t("common.delete"),
      exact: true,
    }),
  ).toBeEnabled();
  expect(bar).toHaveFocus();
});

test("an empty read-only list does not invite an unavailable creation action", async () => {
  fetchMock.mockResolvedValueOnce(
    new Response(JSON.stringify({ skills: [], total: 0, available_tags: [] })),
  );
  render(
    <MemoryRouter>
      <SkillsPanel embedded />
    </MemoryRouter>,
  );
  await screen.findByText(i18n.t("skills.noSkills"));
  expect(screen.queryByText(i18n.t("skills.createFirst"))).toBeNull();
  expect(
    screen.queryAllByRole("button", {
      name: i18n.t("skills.newSkill"),
      exact: true,
    }),
  ).toHaveLength(0);
});
