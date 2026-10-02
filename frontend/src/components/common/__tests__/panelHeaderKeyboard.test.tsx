/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { PanelHeader } from "../PanelHeader";
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(cleanup);
test("mobile actions have a translated label and Escape returns focus to the trigger", () => {
  render(
    <PanelHeader
      title="Tools"
      actions={
        <>
          <button>New tool</button>
          <button>Import</button>
        </>
      }
    />,
  );
  const trigger = screen.getByRole("button", {
    name: "common.filtersAndActions",
  });
  fireEvent.click(trigger);
  expect(trigger.getAttribute("aria-expanded")).toBe("true");
  fireEvent.keyDown(document, { key: "Escape" });
  expect(trigger.getAttribute("aria-expanded")).toBe("false");
  expect(document.activeElement).toBe(trigger);
});

test.each([false, true])(
  "single header action is direct with search=%s",
  (hasSearch) => {
    const run = vi.fn();
    render(
      <PanelHeader
        title="Tools"
        actions={
          <>
            <button onClick={run}>New tool</button>
            {false}
          </>
        }
        onSearchChange={hasSearch ? vi.fn() : undefined}
      />,
    );
    expect(
      screen.queryByRole("button", { name: "common.filtersAndActions" }),
    ).toBeNull();
    const buttons = screen.getAllByRole("button", { name: "New tool" });
    fireEvent.click(buttons[buttons.length - 1]);
    expect(run).toHaveBeenCalledOnce();
  },
);

test("a lone search filter is exposed without another menu", () => {
  render(
    <PanelHeader
      title="Tools"
      onSearchChange={vi.fn()}
      searchAccessory={<button>Filter</button>}
    />,
  );
  expect(
    screen.queryByRole("button", { name: "common.filtersAndActions" }),
  ).toBeNull();
  expect(screen.getAllByRole("button", { name: "Filter" })).toHaveLength(1);
});

test("grouped header actions keep their wrapper behavior in the menu", () => {
  const groupClick = vi.fn();
  render(
    <PanelHeader
      title="Tools"
      actions={
        <div onClick={groupClick}>
          <button>Export</button>
          <button>Import</button>
        </div>
      }
    />,
  );
  fireEvent.click(
    screen.getByRole("button", { name: "common.filtersAndActions" }),
  );
  fireEvent.click(screen.getAllByRole("button", { name: "Export" }).at(-1)!);
  expect(groupClick).toHaveBeenCalledOnce();
});
