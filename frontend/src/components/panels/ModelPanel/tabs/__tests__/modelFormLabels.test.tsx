/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
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
vi.mock("../../../../../services/api/model", () => ({
  modelApi: { listProviders: async () => [] },
}));
vi.mock("../../../../../services/api/pricing", () => ({
  pricingApi: { lookup: vi.fn() },
}));
afterEach(cleanup);

test("model fields are named by their visible labels", async () => {
  const user = userEvent.setup();
  render(
    <ModelFormModal
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
