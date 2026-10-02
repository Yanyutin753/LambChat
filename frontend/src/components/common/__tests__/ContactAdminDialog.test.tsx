/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";
import type { SettingsResponse } from "../../../types";

const listSettings = vi.fn();
vi.mock("../../../services/api", () => ({
  settingsApi: { list: (...args: unknown[]) => listSettings(...args) },
  getAccessToken: () => "contact-preview-token",
}));
import { ContactAdminDialog } from "../ContactAdminDialog";

function settings(email = "", url = ""): SettingsResponse {
  return {
    settings: {
      frontend: [
        { key: "ADMIN_CONTACT_EMAIL", value: email },
        { key: "ADMIN_CONTACT_URL", value: url },
      ],
    },
  } as SettingsResponse;
}
beforeEach(async () => {
  await i18n.changeLanguage("zh");
  listSettings.mockReset();
});
afterEach(cleanup);

test("contact loading does not announce missing information and resolves to complete links", async () => {
  let resolve!: (response: SettingsResponse) => void;
  listSettings.mockReturnValue(
    new Promise<SettingsResponse>((done) => {
      resolve = done;
    }),
  );
  render(
    <ContactAdminDialog isOpen onClose={vi.fn()} reason="emailActivation" />,
  );
  expect(screen.getByRole("status")).toHaveTextContent(/加载/);
  expect(screen.queryByText(/暂无管理员联系方式/)).toBeNull();
  const email = `${"research-support".repeat(8)}@example.test`;
  await act(async () =>
    resolve(settings(email, "https://example.test/support")),
  );
  expect(screen.getByRole("link", { name: email })).toHaveAttribute(
    "href",
    `mailto:${email}`,
  );
  const support = screen.getByRole("link", { name: "联系管理员" });
  expect(support).toHaveAttribute("rel", "noopener noreferrer");
  expect(screen.queryByRole("status")).toBeNull();
});

test("contact read failure remains visible and retry reloads the actual settings hook", async () => {
  listSettings.mockRejectedValueOnce(new Error("Contact read unavailable"));
  render(<ContactAdminDialog isOpen onClose={vi.fn()} />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Contact read unavailable",
  );
  expect(screen.queryByText(/暂无管理员联系方式/)).toBeNull();
  let resolve!: (response: SettingsResponse) => void;
  listSettings.mockReturnValueOnce(
    new Promise<SettingsResponse>((done) => {
      resolve = done;
    }),
  );
  const retry = screen.getByRole("button", { name: "重试" });
  retry.focus();
  fireEvent.click(retry);
  expect(screen.getByRole("dialog")).toHaveFocus();
  expect(screen.getByRole("status")).toBeTruthy();
  await act(async () => resolve(settings("support@example.test")));
  expect(
    await screen.findByRole("link", { name: "support@example.test" }),
  ).toBeTruthy();
  expect(screen.queryByRole("alert")).toBeNull();
  expect(listSettings).toHaveBeenCalledTimes(2);
});

test("loaded empty contact information uses the labelled shared dialog and closes with Escape", async () => {
  listSettings.mockResolvedValue(settings());
  const onClose = vi.fn();
  render(
    <ContactAdminDialog isOpen onClose={onClose} reason="emailActivation" />,
  );
  await waitFor(() =>
    expect(screen.getByText(/暂无管理员联系方式/)).toBeTruthy(),
  );
  expect(screen.getByRole("dialog", { name: "邮箱验证问题" })).toBeTruthy();
  expect(screen.getAllByRole("button")).toHaveLength(1);
  fireEvent.keyDown(document, { key: "Escape" });
  expect(onClose).toHaveBeenCalledTimes(1);
});
