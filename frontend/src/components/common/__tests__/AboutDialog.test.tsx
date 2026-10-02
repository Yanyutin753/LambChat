/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";
import { APP_VERSION } from "../../../utils/appVersion";
import type { VersionInfo } from "../../../types";
const getVersion = vi.fn();
const checkVersion = vi.fn();
vi.mock("../../../services/api", () => ({
  versionApi: {
    get: (...args: unknown[]) => getVersion(...args),
    checkForUpdates: (...args: unknown[]) => checkVersion(...args),
  },
}));
import { AboutDialog } from "../AboutDialog";
const info: VersionInfo = {
  app_version: "server-version",
  latest_version: "99.0.0",
  has_update: true,
  release_url: "https://example.test/release",
  github_url: "https://example.test/source",
};
beforeEach(async () => {
  await i18n.changeLanguage("zh");
  getVersion.mockReset();
  checkVersion.mockReset();
});
afterEach(cleanup);

test("initial read keeps the bundled current version visible and announces loading", async () => {
  let resolve!: (value: VersionInfo) => void;
  getVersion.mockReturnValue(
    new Promise<VersionInfo>((done) => {
      resolve = done;
    }),
  );
  render(<AboutDialog isOpen onClose={vi.fn()} />);
  expect(screen.getByText(APP_VERSION)).toBeTruthy();
  expect(screen.getByRole("status")).toHaveTextContent(
    i18n.t("common.loading"),
  );
  expect(screen.queryByText("server-version")).toBeNull();
  await act(async () => resolve(info));
  expect(screen.queryByRole("status")).toBeNull();
});

test("version read failure can retry without hiding the current client version", async () => {
  getVersion.mockRejectedValueOnce(new Error("Version unavailable"));
  checkVersion.mockResolvedValue(info);
  render(<AboutDialog isOpen onClose={vi.fn()} />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Version unavailable",
  );
  expect(screen.getByText(APP_VERSION)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.retry") }));
  expect(await screen.findByText("99.0.0")).toBeTruthy();
  expect(screen.queryByRole("alert")).toBeNull();
});

test("checking keeps the known version and transfers focus before disabling the action", async () => {
  getVersion.mockResolvedValue(info);
  let reject!: (reason: Error) => void;
  checkVersion.mockReturnValue(
    new Promise<VersionInfo>((_, fail) => {
      reject = fail;
    }),
  );
  render(<AboutDialog isOpen onClose={vi.fn()} />);
  await screen.findByText("99.0.0");
  const check = screen.getByRole("button", {
    name: i18n.t("about.checkUpdate"),
  });
  check.focus();
  fireEvent.click(check);
  expect(screen.getByRole("dialog")).toHaveFocus();
  expect(screen.getByText("99.0.0")).toBeTruthy();
  expect(check).toBeDisabled();
  expect(check).toHaveAttribute("aria-busy", "true");
  await act(async () => reject(new Error("Update check unavailable")));
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Update check unavailable",
  );
  expect(screen.getByText("99.0.0")).toBeTruthy();
});

test("release and source actions are native links with safe new-tab semantics", async () => {
  getVersion.mockResolvedValue(info);
  render(<AboutDialog isOpen onClose={vi.fn()} />);
  const release = await screen.findByRole("link", {
    name: i18n.t("about.viewUpdate"),
  });
  expect(release).toHaveAttribute("href", info.release_url);
  expect(release).toHaveAttribute("target", "_blank");
  expect(release).toHaveAttribute("rel", "noopener noreferrer");
  expect(
    screen.getByRole("link", { name: i18n.t("about.viewOnGitHub") }),
  ).toHaveAttribute("href", info.github_url);
});
