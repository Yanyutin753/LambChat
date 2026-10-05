/** @vitest-environment jsdom */
import { fireEvent, render, screen, cleanup, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { SettingsCategoryNav } from "../SettingsCategoryNav";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(cleanup);

test("desktop navigation exposes current category and selects another category", () => {
  const onSelect = vi.fn();
  render(
    <SettingsCategoryNav
      categories={[
        { category: "frontend", count: 2 },
        { category: "llm", count: 3 },
      ]}
      activeCategory="frontend"
      searching={false}
      labels={{ frontend: "Appearance", llm: "Models" }}
      onSelect={onSelect}
    />,
  );
  expect(
    screen
      .getByRole("button", { name: /Appearance/ })
      .getAttribute("aria-current"),
  ).toBe("page");
  fireEvent.click(screen.getByRole("button", { name: /Models/ }));
  expect(onSelect).toHaveBeenCalledWith("llm");
});

test("mobile picker includes every visible category under a labeled group", () => {
  const onSelect = vi.fn();
  render(
    <SettingsCategoryNav
      mobile
      categories={[
        { category: "frontend", count: 2 },
        { category: "llm", count: 3 },
      ]}
      activeCategory="frontend"
      searching={false}
      labels={{ frontend: "Appearance", llm: "Models" }}
      onSelect={onSelect}
    />,
  );
  const picker = screen.getByRole("button", {
    name: "settings.navigation.browse",
    description: "Appearance · 2",
  });
  fireEvent.click(picker);
  expect(screen.getAllByRole("group")).toHaveLength(2);
  const group = screen.getByRole("group", {
    name: "settings.navigation.groups.intelligence",
  });
  fireEvent.click(within(group).getByRole("option", { name: "Models · 3" }));
  expect(screen.queryByRole("listbox")).toBeNull();
  expect(picker).toHaveFocus();
  expect(onSelect).toHaveBeenCalledWith("llm");
});

test("global search does not falsely mark one category as current", () => {
  render(
    <SettingsCategoryNav
      categories={[{ category: "frontend", count: 2 }]}
      activeCategory="frontend"
      searching
      labels={{ frontend: "Appearance" }}
      onSelect={vi.fn()}
    />,
  );
  expect(screen.getByRole("button", { name: /Appearance/ }).hasAttribute("aria-current")).toBe(false);
});

test("mobile search shows its placeholder and lets users return to a category", () => {
  const onSelect = vi.fn();
  render(
    <SettingsCategoryNav
      mobile
      categories={[{ category: "frontend", count: 2 }]}
      activeCategory="frontend"
      searching
      labels={{ frontend: "Appearance" }}
      onSelect={onSelect}
    />,
  );
  fireEvent.click(screen.getByRole("button", {
    name: "settings.navigation.browse",
    description: "settings.navigation.searchResults",
  }));
  const option = screen.getByRole("option", { name: "Appearance · 2" });
  expect(option).toHaveAttribute("aria-selected", "false");
  fireEvent.click(option);
  expect(onSelect).toHaveBeenCalledWith("frontend");
});

test("mobile category picker is disabled when no categories are visible", () => {
  render(
    <SettingsCategoryNav
      mobile
      categories={[]}
      activeCategory="frontend"
      searching={false}
      labels={{}}
      onSelect={vi.fn()}
    />,
  );
  expect(screen.getByRole("button", {
    name: "settings.navigation.browse",
  })).toBeDisabled();
});

const collapseProps = {
  categories: [
    { category: "frontend" as const, count: 4 },
    { category: "tools" as const, count: 35 },
  ],
  activeCategory: "frontend" as const,
  searching: false,
  labels: { frontend: "Frontend", tools: "Tools" },
  onSelect: vi.fn(),
};
const experienceName = "settings.navigation.groups.experience";

test("groups start expanded and collapse independently without changing selection", async () => {
  const user = userEvent.setup();
  const onSelect = vi.fn();
  render(<SettingsCategoryNav {...collapseProps} onSelect={onSelect} />);
  const toggle = screen.getByRole("button", { name: experienceName });
  expect(toggle).toHaveAttribute("aria-expanded", "true");
  const content = document.getElementById(toggle.getAttribute("aria-controls")!);
  expect(content).toBeVisible();
  await user.click(toggle);
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  expect(content).not.toBeVisible();
  expect(screen.queryByRole("button", { name: /Frontend\s*4/ })).toBeNull();
  expect(screen.getByRole("button", { name: /Tools\s*35/ })).toBeVisible();
  expect(onSelect).not.toHaveBeenCalled();
  await user.click(toggle);
  expect(screen.getByRole("button", { name: /Frontend\s*4/ })).toHaveAttribute("aria-current", "page");
});

test("group headings toggle with Enter and Space", async () => {
  const user = userEvent.setup();
  render(<SettingsCategoryNav {...collapseProps} />);
  await user.tab();
  const toggle = screen.getByRole("button", { name: experienceName });
  expect(toggle).toHaveFocus();
  await user.keyboard("{Enter}");
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  await user.keyboard(" ");
  expect(toggle).toHaveAttribute("aria-expanded", "true");
});

test("search exposes collapsed categories and restores folding when search ends", async () => {
  const user = userEvent.setup();
  const { rerender } = render(<SettingsCategoryNav {...collapseProps} />);
  await user.click(screen.getByRole("button", { name: experienceName }));
  rerender(<SettingsCategoryNav {...collapseProps} searching />);
  const toggle = screen.getByRole("button", { name: experienceName });
  expect(toggle).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByRole("button", { name: /Frontend\s*4/ })).toBeVisible();
  await user.click(toggle);
  expect(screen.getByRole("button", { name: /Frontend\s*4/ })).toBeVisible();
  rerender(<SettingsCategoryNav {...collapseProps} />);
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByRole("button", { name: /Frontend\s*4/ })).toBeNull();
});
