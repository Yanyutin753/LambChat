/** @vitest-environment jsdom */
import { fireEvent, render, screen, cleanup } from "@testing-library/react";
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
  const picker = screen.getByRole("combobox");
  expect(screen.getAllByRole("group")).toHaveLength(2);
  fireEvent.change(picker, { target: { value: "llm" } });
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
  expect(screen.getByRole("button").hasAttribute("aria-current")).toBe(false);
});
