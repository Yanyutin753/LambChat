/** @vitest-environment jsdom */
import { useState } from "react";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { PanelHeader } from "../../common/PanelHeader";
import { SkillFilterDropdown } from "../SkillFilterDropdown";

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

function Filters() {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("enabled");
  const [tags, setTags] = useState<string[]>([]);
  return (
    <PanelHeader
      title="Skills"
      searchValue=""
      onSearchChange={() => {}}
      searchPlaceholder="Search skills"
      actions={<button>New skill</button>}
      searchAccessory={
        <SkillFilterDropdown
          isOpen={open}
          label="Filter"
          activeCount={tags.length}
          options={[
            { value: "all", label: "All" },
            { value: "enabled", label: "Enabled" },
            { value: "disabled", label: "Disabled" },
          ]}
          value={value}
          tags={["Research", "Engineering"]}
          selectedTags={tags}
          tagsLabel="Tags"
          clearLabel="Clear filters"
          onOpenChange={setOpen}
          onValueChange={setValue}
          onToggleTag={(tag) =>
            setTags(
              tags.includes(tag)
                ? tags.filter((t) => t !== tag)
                : [...tags, tag],
            )
          }
          onClearFilters={() => setTags([])}
        />
      }
    />
  );
}

async function openFilters() {
  const { container } = render(<Filters />);
  const more = screen.getByRole("button", { name: "common.filtersAndActions" });
  await userEvent.click(more);
  const trigger = within(
    container.querySelector<HTMLElement>(".panel-header__mobile-menu")!,
  ).getByRole("button", { name: "Filter" });
  await userEvent.click(trigger);
  return { trigger, more };
}

test("nested filters focus the selected option and Escape closes only that layer", async () => {
  const { trigger, more } = await openFilters();
  expect(screen.getByRole("menuitemradio", { name: "Enabled" })).toHaveFocus();
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("menu", { name: "Filter" })).toBeNull();
  expect(more).toHaveAttribute("aria-expanded", "true");
  expect(trigger).toHaveFocus();
  await userEvent.keyboard("{Escape}");
  expect(more).toHaveAttribute("aria-expanded", "false");
  expect(more).toHaveFocus();
});

test("filter keyboard navigation and multi-selection keep the active menu usable", async () => {
  await openFilters();
  await userEvent.keyboard("{End}");
  const engineering = screen.getByRole("menuitemcheckbox", {
    name: "Engineering",
  });
  expect(engineering).toHaveFocus();
  await userEvent.keyboard(" ");
  expect(engineering).toHaveAttribute("aria-checked", "true");
  expect(engineering).toHaveFocus();
  await userEvent.keyboard("{Home}");
  expect(screen.getByRole("menuitemradio", { name: "All" })).toHaveFocus();
});

test("Tab leaves the filter menu through its trigger and keeps the parent actions open", async () => {
  const { more } = await openFilters();
  await userEvent.tab();
  expect(screen.queryByRole("menu", { name: "Filter" })).toBeNull();
  expect(
    screen.getAllByRole("button", { name: "New skill" }).at(-1),
  ).toHaveFocus();
  expect(more).toHaveAttribute("aria-expanded", "true");
});

test("clearing filters preserves keyboard ownership after its action disappears", async () => {
  const { more } = await openFilters();
  await userEvent.keyboard("{End} ");
  await userEvent.keyboard("{Home}{ArrowDown}{ArrowDown}{ArrowDown}{Enter}");
  const menu = screen.getByRole("menu", { name: "Filter" });
  expect(screen.queryByRole("menuitem", { name: "Clear filters" })).toBeNull();
  expect(menu).toHaveFocus();
  await userEvent.keyboard("{ArrowUp}");
  expect(
    screen.getByRole("menuitemcheckbox", { name: "Engineering" }),
  ).toHaveFocus();
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("menu", { name: "Filter" })).toBeNull();
  expect(more).toHaveAttribute("aria-expanded", "true");
});

test("short-screen filters use the available space above the trigger", async () => {
  vi.spyOn(window, "innerHeight", "get").mockReturnValue(300);
  await openFilters();
  const menu = screen.getByRole("menu", { name: "Filter" });
  expect(menu.style.top).toBe("");
  expect(menu.style.bottom).toBe("128px");
  expect(menu.style.maxHeight).toBe("160px");
});
