/** @vitest-environment jsdom */
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import i18n from "../../../../../i18n";
import { modelApi } from "../../../../../services/api/model";
import { BatchCreateModal } from "../BatchCreateModal";

vi.mock("../../../../common/EditorSidebar", () => ({
  EditorSidebar: ({
    children,
    footer,
  }: {
    children: React.ReactNode;
    footer: React.ReactNode;
  }) => (
    <div>
      {children}
      <div role="group" aria-label="Editor actions">
        {footer}
      </div>
    </div>
  ),
}));
vi.mock("../../../../../services/api/model", () => ({
  modelApi: { listProviders: async () => [], importModels: vi.fn() },
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

test("batch rows have independent named fields including advanced prices", async () => {
  const user = userEvent.setup();
  render(<BatchCreateModal onClose={vi.fn()} onSaved={vi.fn()} />);
  expect(
    screen.getByRole("button", { name: i18n.t("agentConfig.modelApiFormat") }),
  ).toBeInTheDocument();
  await user.click(
    screen.getByRole("button", { name: i18n.t("agentConfig.batchAddRow") }),
  );
  const rows = screen.getAllByRole("group", { name: /#/ });
  expect(rows).toHaveLength(2);
  for (const row of rows) {
    await user.click(
      within(row).getByText(i18n.t("agentConfig.advancedConfig")),
    );
    for (const key of [
      "modelValue",
      "modelLabel",
      "modelDescription",
      "modelApiKey",
      "modelApiBase",
      "temperature",
      "maxTokens",
      "maxInputTokens",
      "pricingInput",
      "pricingOutput",
      "pricingCacheRead",
      "pricingCacheWrite",
    ]) {
      expect(
        within(row).getByLabelText(
          (text) =>
            text === i18n.t(`agentConfig.${key}`) ||
            text === `${i18n.t(`agentConfig.${key}`)} *`,
        ),
      ).toBeInTheDocument();
    }
    expect(
      within(row).getByRole("checkbox", {
        name: i18n.t("agentConfig.imageUrlModeBase64"),
      }),
    ).toBeInTheDocument();
    expect(
      within(row).getByText(i18n.t("agentConfig.imageUrlModeHint")),
    ).toBeInTheDocument();
  }
  const values = screen.getAllByLabelText(
    `${i18n.t("agentConfig.modelValue")} *`,
  );
  expect(values[0].id).not.toBe(values[1].id);
  await user.click(
    screen.getByRole("button", { name: `${i18n.t("common.delete")} #2` }),
  );
  expect(values[0]).toHaveFocus();
  expect(screen.getAllByRole("group", { name: /#/ })).toHaveLength(1);
});

test("a rejected row import keeps the draft, exposes a persistent error, and can retry", async () => {
  const user = userEvent.setup();
  const saved = vi.fn();
  vi.mocked(modelApi.importModels)
    .mockRejectedValueOnce(new Error("Import unavailable"))
    .mockResolvedValueOnce({} as never);
  render(<BatchCreateModal onClose={vi.fn()} onSaved={saved} />);
  await user.type(
    screen.getByLabelText(`${i18n.t("agentConfig.modelValue")} *`),
    "test-model",
  );
  await user.type(
    screen.getByLabelText(`${i18n.t("agentConfig.modelLabel")} *`),
    "Test model",
  );
  const submit = screen.getByRole("button", {
    name: i18n.t("agentConfig.batchCreateBtn", { count: 1 }),
  });
  await user.click(submit);
  expect(
    await within(
      screen.getByRole("group", { name: "Editor actions" }),
    ).findByRole("alert"),
  ).toHaveTextContent("Import unavailable");
  expect(screen.getByRole("alert")).toHaveAttribute("tabindex", "0");
  expect(
    screen.getByLabelText(`${i18n.t("agentConfig.modelValue")} *`),
  ).toHaveValue("test-model");
  await user.click(submit);
  expect(saved).toHaveBeenCalledOnce();
  expect(screen.queryByRole("alert")).toBeNull();
});

test("JSON import has a keyboard file entry and communicates invalid input", async () => {
  const user = userEvent.setup();
  render(
    <BatchCreateModal
      initialTab="jsonImport"
      onClose={vi.fn()}
      onSaved={vi.fn()}
    />,
  );
  const fileInput = screen.getByLabelText(
    i18n.t("agentConfig.batchDropzoneTitle"),
  );
  const click = vi.spyOn(fileInput, "click");
  await user.type(
    screen.getByRole("button", {
      name: new RegExp(i18n.t("agentConfig.batchDropzoneTitle")),
    }),
    "{Enter}",
  );
  expect(click).toHaveBeenCalled();
  const json = screen.getByLabelText(i18n.t("agentConfig.batchJsonLabel"));
  await user.type(json, "invalid JSON");
  expect(json).toHaveAttribute("aria-invalid", "true");
  expect(screen.getByRole("status")).toHaveTextContent(
    i18n.t("agentConfig.batchJsonError"),
  );
});

test("invalid shared headers stay visible beside the import action without sending a request", async () => {
  const user = userEvent.setup();
  render(
    <BatchCreateModal
      initialTab="jsonImport"
      onClose={vi.fn()}
      onSaved={vi.fn()}
    />,
  );
  await user.type(
    screen.getByLabelText(i18n.t("agentConfig.modelRequestHeaders")),
    "invalid headers",
  );
  await user.click(screen.getByLabelText(i18n.t("agentConfig.batchJsonLabel")));
  await user.paste(
    JSON.stringify([{ value: "test-model", label: "Test model" }]),
  );
  await user.click(
    screen.getByRole("button", { name: i18n.t("agentConfig.batchImportBtn") }),
  );
  expect(
    await within(
      screen.getByRole("group", { name: "Editor actions" }),
    ).findByRole("alert"),
  ).toHaveTextContent(i18n.t("agentConfig.requestHeadersInvalidJson"));
  expect(modelApi.importModels).not.toHaveBeenCalled();
  expect(
    screen.getByLabelText(i18n.t("agentConfig.modelRequestHeaders")),
  ).toHaveValue("invalid headers");
});
