/** @vitest-environment jsdom */
import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { ProfileModal } from "../ProfileModal";
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => ({ logout: vi.fn() }),
}));
vi.mock("../../../hooks/useSwipeToClose", () => ({
  useSwipeToClose: () => ({ current: null }),
}));
vi.mock("../tabs/ProfileInfoTab", () => ({
  ProfileInfoTab: () => <p>Account content</p>,
}));
vi.mock("../tabs/ProfileNotificationTab", () => ({
  ProfileNotificationTab: () => null,
}));
vi.mock("../tabs/ProfilePreferencesTab", () => ({
  ProfilePreferencesTab: () => null,
}));
vi.mock("../tabs/ProfileEnvVarsTab", () => ({
  ProfileEnvVarsTab: () => <p>Environment content</p>,
}));
vi.mock("../tabs/ProfileToolsTab", () => ({ ProfileToolsTab: () => null }));
vi.mock("../tabs/ProfileModelsTab", () => ({ ProfileModelsTab: () => null }));
vi.mock("../tabs/ProfileTermsTab", () => ({ ProfileTermsTab: () => null }));
test("a single labelled dialog lets narrow screens select every settings category", () => {
  Element.prototype.scrollIntoView = vi.fn();
  const close = vi.fn();
  const { unmount } = render(
    <ProfileModal showProfileModal onCloseProfileModal={close} />,
  );
  expect(screen.getAllByRole("dialog")).toHaveLength(1);
  expect(
    screen.getByRole("heading", { name: "profile.title" }).className,
  ).toContain("font-serif");
  const selector = screen
    .getAllByRole("button", { name: "profile.preferences" })
    .find((button) => button.hasAttribute("aria-haspopup"))!;
  fireEvent.click(selector);
  expect(screen.getAllByRole("option")).toHaveLength(7);
  fireEvent.click(screen.getByRole("option", { name: "envVars.title" }));
  expect(screen.getByText("Environment content")).toBeTruthy();
  expect(screen.queryByText("Account content")).toBeNull();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(close).toHaveBeenCalledOnce();
  unmount();
});
