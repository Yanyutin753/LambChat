/** @vitest-environment jsdom */
import { useRef, useState } from "react";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { PanelHeader } from "../../common/PanelHeader";
import { PersonaScopeDropdown } from "../PersonaScopeDropdown";
import { PersonaTagFilterDropdown } from "../PersonaTagFilterDropdown";
import type { ScopeFilter } from "../usePersonaPlaza";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
    top: 180,
    bottom: 224,
    left: 12,
    right: 308,
    width: 296,
    height: 44,
    x: 12,
    y: 180,
    toJSON: () => ({}),
  });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function Filters({ kind }: { kind: "scope" | "tags" }) {
  const [open, setOpen] = useState(false);
  const [scope, setScope] = useState<ScopeFilter>("user");
  const [tag, setTag] = useState<string | null>("Research");
  const triggerRef = useRef<HTMLButtonElement>(null);
  return (
    <>
      <PanelHeader
        title="Personas"
        searchValue=""
        onSearchChange={() => {}}
        searchPlaceholder="Search personas"
        actions={<button>New persona</button>}
        searchAccessory={
          <button
            ref={triggerRef}
            aria-haspopup="menu"
            aria-expanded={open}
            onClick={() => setOpen(!open)}
          >
            {kind === "scope" ? "Scope" : "Tags"}
          </button>
        }
      />
      {kind === "scope" ? (
        <PersonaScopeDropdown
          isOpen={open}
          scopeFilter={scope}
          scopeTabs={[
            { key: "all", label: "All", icon: "Users" },
            { key: "user", label: "Mine", icon: "User" },
          ]}
          scopeBtnRef={triggerRef}
          onSelect={setScope}
          onClose={() => setOpen(false)}
        />
      ) : (
        <PersonaTagFilterDropdown
          isOpen={open}
          allTags={["Research", "Engineering"]}
          activeTag={tag}
          hasActiveFilters={!!tag}
          tagBtnRef={triggerRef}
          onToggleTag={(value) => setTag(tag === value ? null : value)}
          onClearFilters={() => setTag(null)}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}

async function openFilter(kind: "scope" | "tags") {
  const { container } = render(<Filters kind={kind} />);
  const more = screen.getByRole("button", { name: "common.filtersAndActions" });
  await userEvent.click(more);
  const trigger = within(
    container.querySelector<HTMLElement>(".panel-header__mobile-menu")!,
  ).getByRole("button", {
    name: kind === "scope" ? "Scope" : "Tags",
    exact: true,
  });
  await userEvent.click(trigger);
  return { more, trigger };
}

test.each(["scope", "tags"] as const)(
  "%s filter owns focus and Escape closes only its layer",
  async (kind) => {
    const { more, trigger } = await openFilter(kind);
    expect(
      screen.getByRole("menuitemradio", {
        name: kind === "scope" ? "Mine" : "Research",
      }),
    ).toHaveFocus();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).toBeNull();
    expect(trigger).toHaveFocus();
    expect(more).toHaveAttribute("aria-expanded", "true");
    await userEvent.keyboard("{Escape}");
    expect(more).toHaveFocus();
    expect(more).toHaveAttribute("aria-expanded", "false");
  },
);

test("scope selection uses arrows and returns to its trigger", async () => {
  const { more, trigger } = await openFilter("scope");
  await userEvent.keyboard("{Home}{Enter}");
  expect(screen.queryByRole("menu")).toBeNull();
  expect(trigger).toHaveFocus();
  expect(more).toHaveAttribute("aria-expanded", "true");
  await userEvent.click(trigger);
  expect(screen.getByRole("menuitemradio", { name: "All" })).toHaveFocus();
});

test("tag selection and disappearing clear action preserve keyboard ownership", async () => {
  const { more } = await openFilter("tags");
  await userEvent.keyboard("{End} ");
  expect(
    screen.getByRole("menuitemradio", { name: "Engineering" }),
  ).toHaveAttribute("aria-checked", "true");
  await userEvent.keyboard("{Home}{Enter}");
  expect(
    screen.queryByRole("menuitem", { name: "personaPresets.clearFilters" }),
  ).toBeNull();
  expect(screen.getByRole("menu")).toHaveFocus();
  await userEvent.keyboard("{ArrowUp}");
  expect(
    screen.getByRole("menuitemradio", { name: "Engineering" }),
  ).toHaveFocus();
  await userEvent.keyboard("{Escape}");
  expect(more).toHaveAttribute("aria-expanded", "true");
});

test.each(["scope", "tags"] as const)(
  "Tab exits %s filter through its trigger",
  async (kind) => {
    const { more } = await openFilter(kind);
    await userEvent.tab();
    expect(screen.queryByRole("menu")).toBeNull();
    expect(
      screen.getAllByRole("button", { name: "New persona" }).at(-1),
    ).toHaveFocus();
    expect(more).toHaveAttribute("aria-expanded", "true");
  },
);

test.each(["scope", "tags"] as const)(
  "%s filter flips into the available short-screen space",
  async (kind) => {
    vi.spyOn(window, "innerHeight", "get").mockReturnValue(300);
    await openFilter(kind);
    const menu = screen.getByRole("menu");
    expect(menu.style.top).toBe("");
    expect(menu.style.bottom).toBe("128px");
    expect(menu.style.maxHeight).toBe("160px");
  },
);
