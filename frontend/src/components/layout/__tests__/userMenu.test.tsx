/** @vitest-environment jsdom */
import { useState } from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";
import { UserMenu } from "../UserMenu";
import { ModalSurface } from "../../common/ModalSurface";

const auth = vi.hoisted(() => ({
  logout: vi.fn(),
  hasAnyPermission: vi.fn(),
  user: { username: "Interface Reviewer" },
}));
vi.mock("../../../hooks/useAuth", () => ({ useAuth: () => auth }));
vi.mock("../../../services/api", () => ({ getFullUrl: (url: string) => url }));
vi.mock("../../chat/ChatMessage/ImageWithSkeleton", () => ({
  ImageWithSkeleton: () => null,
}));
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
beforeEach(async () => {
  await i18n.changeLanguage("en");
  vi.clearAllMocks();
  auth.hasAnyPermission.mockReturnValue(true);
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 1440,
  });
});
function mountMenu(onShowProfile = vi.fn()) {
  render(
    <MemoryRouter>
      <UserMenu onShowProfile={onShowProfile} />
    </MemoryRouter>,
  );
  const trigger = screen.getByRole("button", { name: "Profile", exact: true });
  trigger.focus();
  fireEvent.click(trigger);
  return trigger;
}
test("avatar names its menu and exposes its expanded state", () => {
  const trigger = mountMenu();
  const menu = screen.getByRole("menu", { name: "Profile", exact: true });
  expect(trigger).toHaveAttribute("aria-haspopup", "menu");
  expect(trigger).toHaveAttribute("aria-expanded", "true");
  expect(trigger).toHaveAttribute("aria-controls", menu.id);
  expect(
    screen.getByRole("menuitem", { name: "Profile", exact: true }),
  ).toHaveFocus();
});
test("desktop avatar menu supports arrow keys and Tab continues to the next page action", async () => {
  mountMenu();
  render(<button>Next page action</button>);
  await userEvent.keyboard("{ArrowDown}");
  expect(
    screen.getByRole("menuitem", { name: "Users", exact: true }),
  ).toHaveFocus();
  await userEvent.keyboard("{Tab}");
  expect(screen.queryByRole("menu")).toBeNull();
  expect(
    screen.getByRole("button", { name: "Next page action" }),
  ).toHaveFocus();
});
test("Escape closes the desktop avatar menu without selecting an action", async () => {
  const profile = vi.fn();
  const trigger = mountMenu(profile);
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("menu")).toBeNull();
  expect(trigger).toHaveFocus();
  expect(profile).not.toHaveBeenCalled();
  expect(auth.logout).not.toHaveBeenCalled();
});
test.each([{ isComposing: true }, { keyCode: 229 }])(
  "IME cancellation does not dismiss the avatar menu (%j)",
  (composition) => {
    mountMenu();
    fireEvent.keyDown(document, { key: "Escape", ...composition });
    expect(screen.getByRole("menu")).toBeTruthy();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
  },
);
test("mobile sheet has an explicit close action that returns focus to the avatar", async () => {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 390,
  });
  const trigger = mountMenu();
  const sheet = screen.getByRole("dialog", { name: "Profile", exact: true });
  expect(trigger).toHaveAttribute("aria-haspopup", "dialog");
  await userEvent.click(
    within(sheet).getByRole("button", { name: "Close", exact: true }),
  );
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(trigger).toHaveFocus();
});
test("profile action transfers focus into the new dialog instead of the avatar", async () => {
  const nativeFocus = HTMLElement.prototype.focus;
  vi.spyOn(HTMLElement.prototype, "focus").mockImplementation(function (
    this: HTMLElement,
    options,
  ) {
    if (!this.closest("[inert]")) nativeFocus.call(this, options);
  });
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 390,
  });
  function Harness() {
    const [profile, setProfile] = useState(false);
    return (
      <>
        <UserMenu onShowProfile={() => setProfile(true)} />
        <ModalSurface
          open={profile}
          onClose={() => setProfile(false)}
          label="Personal settings"
        >
          <button onClick={() => setProfile(false)}>
            Close personal settings
          </button>
        </ModalSurface>
      </>
    );
  }
  render(
    <div id="root">
      <MemoryRouter>
        <Harness />
      </MemoryRouter>
    </div>,
  );
  const root = document.getElementById("root")!;
  // jsdom does not implement native inert reflection or its focus boundary.
  Object.defineProperty(root, "inert", {
    configurable: true,
    get: () => root.hasAttribute("inert"),
    set: (value) => root.toggleAttribute("inert", value),
  });
  await userEvent.click(
    screen.getByRole("button", { name: "Profile", exact: true }),
  );
  await userEvent.click(
    within(
      screen.getByRole("dialog", { name: "Profile", exact: true }),
    ).getByRole("button", { name: "Profile", exact: true }),
  );
  const profile = await screen.findByRole("dialog", {
    name: "Personal settings",
  });
  expect(profile.contains(document.activeElement)).toBe(true);
  expect(
    screen.queryByRole("dialog", { name: "Profile", exact: true }),
  ).toBeNull();
  await userEvent.click(
    within(profile).getByRole("button", { name: "Close personal settings" }),
  );
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(
    screen.getByRole("button", { name: "Profile", exact: true }),
  ).toHaveFocus();
});
test("users without administration permissions see only personal actions", () => {
  auth.hasAnyPermission.mockReturnValue(false);
  mountMenu();
  expect(screen.getAllByRole("menuitem").map((e) => e.textContent)).toEqual([
    "Profile",
    "Logout",
  ]);
  expect(screen.queryByText("Admin")).toBeNull();
  expect(screen.queryByText("System")).toBeNull();
});
test("navigation dismisses the menu before changing the page", async () => {
  function Path() {
    return <output aria-label="Current page">{useLocation().pathname}</output>;
  }
  render(
    <MemoryRouter initialEntries={["/agents"]}>
      <UserMenu onShowProfile={vi.fn()} />
      <Path />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Profile", exact: true }));
  await userEvent.click(
    screen.getByRole("menuitem", { name: "Users", exact: true }),
  );
  expect(screen.queryByRole("menu")).toBeNull();
  await waitFor(() =>
    expect(
      screen.getByRole("status", { name: "Current page" }),
    ).toHaveTextContent("/users"),
  );
});
test("resizing dismisses the avatar menu before changing its presentation", () => {
  const trigger = mountMenu();
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 390,
  });
  fireEvent(window, new Event("resize"));
  expect(screen.queryByRole("menu")).toBeNull();
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(trigger).toHaveFocus();
});

test("a resize without an open avatar menu preserves another control's focus", () => {
  render(
    <MemoryRouter>
      <UserMenu onShowProfile={vi.fn()} />
      <button>New dialog action</button>
    </MemoryRouter>,
  );
  const action = screen.getByRole("button", { name: "New dialog action" });
  action.focus();
  fireEvent(window, new Event("resize"));
  expect(action).toHaveFocus();
});
