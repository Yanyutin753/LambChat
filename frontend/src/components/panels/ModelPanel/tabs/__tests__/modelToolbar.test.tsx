/** @vitest-environment jsdom */
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import i18n from "../../../../../i18n";
import { ModelConfigTab } from "../ModelConfigTab";
import { pricingApi } from "../../../../../services/api/pricing";

vi.mock("../BatchCreateModal", () => ({
  BatchCreateModal: ({ initialTab }: { initialTab: string }) => (
    <div role="dialog" aria-label={initialTab} />
  ),
}));
vi.mock("../../../../../services/api/pricing", () => ({
  pricingApi: { sync: vi.fn(), backfillUsage: vi.fn() },
}));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

test("secondary model actions share a named menu and return keyboard focus", async () => {
  const user = userEvent.setup();
  render(<ModelConfigTab models={[]} onReload={vi.fn()} />);
  const more = screen.getByRole("button", {
    name: i18n.t("common.moreOptions"),
  });
  await user.click(more);
  const menu = screen.getByRole("menu");
  expect(
    within(menu).getByRole("menuitem", {
      name: i18n.t("agentConfig.exportModels"),
    }),
  ).toBeDisabled();
  expect(
    within(menu).getByRole("menuitem", {
      name: i18n.t("agentConfig.importModels"),
    }),
  ).toHaveFocus();
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("menu")).toBeNull();
  expect(more).toHaveFocus();
  await user.click(more);
  await user.click(
    screen.getByRole("menuitem", { name: i18n.t("agentConfig.importModels") }),
  );
  expect(
    screen.getByRole("dialog", { name: "jsonImport" }),
  ).toBeInTheDocument();
  expect(screen.queryByRole("menu")).toBeNull();
});

test("a pending price sync cannot be repeated and a failed sync can be retried", async () => {
  const user = userEvent.setup();
  let rejectSync!: (error: Error) => void;
  vi.mocked(pricingApi.sync).mockImplementationOnce(
    () =>
      new Promise((_, reject) => {
        rejectSync = reject;
      }),
  );
  render(<ModelConfigTab models={[]} onReload={vi.fn()} />);
  const more = screen.getByRole("button", {
    name: i18n.t("common.moreOptions"),
  });
  await user.click(more);
  await user.click(
    screen.getByRole("menuitem", { name: i18n.t("agentConfig.pricingSync") }),
  );
  await user.click(more);
  expect(
    screen.getByRole("menuitem", { name: i18n.t("agentConfig.pricingSync") }),
  ).toBeDisabled();
  rejectSync(new Error("Sync unavailable"));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Sync unavailable",
  );
  expect(
    screen.getByRole("menuitem", { name: i18n.t("agentConfig.pricingSync") }),
  ).toBeEnabled();
});
