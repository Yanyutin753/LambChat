/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, expect, test, vi } from "vitest";
import { PanelHeader } from "../PanelHeader";
import { EditorSidebar } from "../EditorSidebar";
import { ModalSurface } from "../ModalSurface";
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(cleanup);
test("mobile actions have a translated label and Escape returns focus to the trigger", () => {
  render(<PanelHeader title="Tools" actions={<button>New tool</button>} />);
  const trigger = screen.getByRole("button", {
    name: "common.filtersAndActions",
  });
  fireEvent.click(trigger);
  expect(trigger.getAttribute("aria-expanded")).toBe("true");
  fireEvent.keyDown(document, { key: "Escape" });
  expect(trigger.getAttribute("aria-expanded")).toBe("false");
  expect(document.activeElement).toBe(trigger);
});

test.each(["editor", "modal"])(
  "closing a %s opened from mobile actions returns focus to the surviving trigger",
  async (presentation) => {
    function Imports() {
      const [open, setOpen] = useState(false);
      return (
        <main data-panel="skills">
          <PanelHeader
            title="Skills"
            actions={<button onClick={() => setOpen(true)}>Import</button>}
            searchValue=""
            onSearchChange={() => {}}
            searchPlaceholder="Search skills"
          />
          {presentation === "editor" ? (
            <EditorSidebar
              open={open}
              onClose={() => setOpen(false)}
              title="Import"
            >
              <button onClick={() => setOpen(false)}>Close import</button>
            </EditorSidebar>
          ) : (
            <ModalSurface
              open={open}
              onClose={() => setOpen(false)}
              label="Import"
            >
              <button onClick={() => setOpen(false)}>Close import</button>
            </ModalSurface>
          )}
        </main>
      );
    }
    const { container } = render(<Imports />);
    const trigger = screen.getByRole("button", {
      name: "common.filtersAndActions",
    });
    await userEvent.click(trigger);
    const menu = container.querySelector<HTMLElement>(
      ".panel-header__mobile-menu",
    )!;
    await userEvent.click(
      within(menu).getByRole("button", { name: "Import", exact: true }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Close import" }));
    await waitFor(() => expect(trigger).toHaveFocus());
  },
);

test("closing mobile actions preserves focus already moved by its action", async () => {
  const { container } = render(
    <>
      <button id="destination">Destination</button>
      <PanelHeader
        title="Tools"
        actions={
          <button
            onClick={() => document.getElementById("destination")?.focus()}
          >
            Navigate
          </button>
        }
      />
    </>,
  );
  await userEvent.click(
    screen.getByRole("button", { name: "common.filtersAndActions" }),
  );
  await userEvent.click(
    within(
      container.querySelector<HTMLElement>(".panel-header__mobile-menu")!,
    ).getByRole("button", { name: "Navigate" }),
  );
  expect(screen.getByRole("button", { name: "Destination" })).toHaveFocus();
});
