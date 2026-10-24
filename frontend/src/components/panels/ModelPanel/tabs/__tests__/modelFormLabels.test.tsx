/** @vitest-environment jsdom */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import i18n from "../../../../../i18n";
import { ModelFormModal } from "../ModelFormModal";

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
      {footer}
    </div>
  ),
}));
const modelMocks = vi.hoisted(() => ({
  update: vi.fn(async (_id: string, _data: unknown) => ({})),
}));
vi.mock("../../../../../services/api/model", () => ({
  modelApi: { listProviders: async () => [], update: modelMocks.update },
}));
vi.mock("../../../../../services/api/pricing", () => ({
  pricingApi: { lookup: vi.fn() },
}));
afterEach(cleanup);

test("model fields are named by their visible labels", async () => {
  const user = userEvent.setup();
  render(
    <ModelFormModal
      canManagePricing={true}
      model={null}
      models={[]}
      onClose={vi.fn()}
      onSaved={vi.fn()}
    />,
  );
  await user.click(screen.getByText(i18n.t("agentConfig.advancedConfig")));
  for (const key of [
    "modelValue",
    "modelLabel",
    "pricingInput",
    "pricingOutput",
    "pricingCacheRead",
    "pricingCacheWrite",
    "modelDescription",
    "modelApiKey",
    "modelApiBase",
    "modelRequestHeaders",
    "temperature",
    "maxTokens",
    "maxInputTokens",
  ]) {
    expect(
      screen.getByLabelText(
        (text) =>
          text === i18n.t(`agentConfig.${key}`) ||
          text === `${i18n.t(`agentConfig.${key}`)} *`,
      ),
    ).toBeTruthy();
  }
  for (const key of ["fallbackModel", "modelApiFormat", "imageUrlMode"]) {
    expect(
      screen.getByRole("button", { name: i18n.t(`agentConfig.${key}`) }),
    ).toBeTruthy();
  }
});

test("model maintainers save metadata without submitting pricing", async () => {
  const user = userEvent.setup();
  render(
    <ModelFormModal
      model={{
        id: "m1",
        value: "model-1",
        label: "Model",
        enabled: true,
        order: 0,
        pricing: { input: 1 },
      }}
      models={[]}
      canManagePricing={false}
      onClose={vi.fn()}
      onSaved={vi.fn()}
    />,
  );
  await user.click(screen.getByRole("button", { name: i18n.t("common.save") }));
  await waitFor(() => expect(modelMocks.update).toHaveBeenCalled());
  expect(modelMocks.update.mock.calls.at(-1)?.[1]).not.toHaveProperty(
    "pricing",
  );
  expect(
    screen.queryByLabelText(i18n.t("agentConfig.pricingInput")),
  ).toBeNull();
});
