/** @vitest-environment jsdom */
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import i18n from "../../../../../i18n";
import { GlobalAgentTab } from "../GlobalAgentTab";

vi.mock("../../../../common/EditorSidebar", () => ({
  EditorSidebar: ({
    children,
    footer,
    title,
  }: {
    children: React.ReactNode;
    footer: React.ReactNode;
    title: string;
  }) => (
    <div role="dialog" aria-label={title}>
      {children}
      <div role="group" aria-label="Editor actions">
        {footer}
      </div>
    </div>
  ),
}));
afterEach(cleanup);

test("localized agent fields retain separate drafts and expose the selected language", async () => {
  const user = userEvent.setup();
  render(
    <GlobalAgentTab
      agents={[
        {
          id: "custom",
          name: "Test assistant",
          description: "",
          enabled: true,
        },
      ]}
      onUpdate={vi.fn()}
      isLoading={false}
      isSaving={false}
    />,
  );
  await user.click(screen.getByRole("button", { name: "Test assistant" }));
  expect(
    screen.getByLabelText(i18n.t("agentConfig.sortOrder")),
  ).toHaveAttribute("type", "number");
  await user.click(screen.getByRole("button", { name: "ZH", exact: true }));
  await user.type(
    screen.getByLabelText(i18n.t("agentConfig.displayName", { lng: "zh" })),
    "中文草稿",
  );
  await user.click(screen.getByRole("button", { name: "EN", exact: true }));
  expect(
    screen.getByRole("button", { name: "EN", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("button", { name: "EN", exact: true })).toHaveClass(
    "ui-button--secondary",
  );
  await user.type(
    screen.getByLabelText(i18n.t("agentConfig.displayName", { lng: "en" })),
    "English draft",
  );
  await user.click(screen.getByRole("button", { name: "ZH", exact: true }));
  expect(
    screen.getByLabelText(i18n.t("agentConfig.displayName", { lng: "zh" })),
  ).toHaveValue("中文草稿");
  expect(
    screen.getByLabelText(
      i18n.t("agentConfig.displayDescription", { lng: "zh" }),
    ),
  ).toBeInTheDocument();
});

test("a rejected save keeps the localized draft visible and can be retried", async () => {
  const user = userEvent.setup();
  const update = vi
    .fn()
    .mockRejectedValueOnce(new Error("Save unavailable"))
    .mockResolvedValueOnce(undefined);
  render(
    <GlobalAgentTab
      agents={[
        {
          id: "custom",
          name: "Test assistant",
          description: "",
          enabled: true,
        },
      ]}
      onUpdate={update}
      isLoading={false}
      isSaving={false}
    />,
  );
  await user.click(screen.getByRole("button", { name: "Test assistant" }));
  await user.click(screen.getByRole("button", { name: "EN", exact: true }));
  await user.type(
    screen.getByLabelText(i18n.t("agentConfig.displayName", { lng: "en" })),
    "Draft name",
  );
  const editor = screen.getByRole("dialog");
  await user.click(
    within(editor).getByRole("button", { name: i18n.t("common.save") }),
  );
  expect(
    await within(
      screen.getByRole("group", { name: "Editor actions" }),
    ).findByRole("alert"),
  ).toHaveTextContent("Save unavailable");
  expect(
    screen.getByLabelText(i18n.t("agentConfig.displayName", { lng: "en" })),
  ).toHaveValue("Draft name");
  await user.click(
    within(editor).getByRole("button", { name: i18n.t("common.save") }),
  );
  expect(within(editor).queryByRole("alert")).toBeNull();
  expect(update).toHaveBeenCalledTimes(2);
});
