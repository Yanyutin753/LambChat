/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, within } from "@testing-library/react";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import { afterEach, expect, test } from "vitest";
import zh from "../../../../../i18n/locales/zh.json";
import { ImageGenerateItem } from "../ImageGenerateItem";
import {
  closeAllPersistentToolPanels,
  getPersistentToolPanelState,
} from "../persistentToolPanelState";

const i18n = createInstance();
await i18n.init({
  lng: "zh",
  resources: { zh: { translation: zh } },
  interpolation: { escapeValue: false },
});

afterEach(() => {
  cleanup();
  closeAllPersistentToolPanels();
});

function show(props: React.ComponentProps<typeof ImageGenerateItem>) {
  const view = render(
    <I18nextProvider i18n={i18n}>
      <ImageGenerateItem {...props} />
    </I18nextProvider>,
  );
  return within(view.container);
}

test.each([false, true])(
  "shows the resolved image model in the chat row and size in its panel (JSON string=%s)",
  (asString) => {
    const result = {
      model: "actual-image-model",
      images: [
        {
          url: "/api/upload/file/generated-images/portrait.png",
          content_type: "image/png",
          size: 2097152,
        },
      ],
    };
    const view = show({
      args: { prompt: "portrait", model: "requested-model" },
      result: asString ? JSON.stringify(result) : result,
      success: true,
    });
    const button = view.getByRole("button");
    expect(within(button).getByText("actual-image-model")).toBeVisible();
    expect(view.queryByText("requested-model")).toBeNull();
    fireEvent.click(button);
    const panel = render(
      <I18nextProvider i18n={i18n}>
        {getPersistentToolPanelState()!.children}
      </I18nextProvider>,
    );
    expect(
      within(panel.container).getByText("actual-image-model"),
    ).toBeVisible();
    expect(within(panel.container).getByText("2.0 MB")).toBeVisible();
    expect(
      within(panel.container).getByRole("button", { name: "portrait.png" }),
    ).toBeInTheDocument();
  },
);

test("shows the requested model while generation is pending", () => {
  const view = show({
    args: { prompt: "portrait", model: "requested-model" },
    isPending: true,
  });
  expect(
    within(view.getByRole("button")).getByText("requested-model"),
  ).toBeVisible();
});

test("old image results with no byte size do not claim to be zero bytes", () => {
  const view = show({
    args: { prompt: "portrait" },
    result: { images: [{ url: "/api/upload/file/old.png" }] },
    success: true,
  });
  fireEvent.click(view.getByRole("button"));
  const panel = render(
    <I18nextProvider i18n={i18n}>
      {getPersistentToolPanelState()!.children}
    </I18nextProvider>,
  );
  expect(within(panel.container).queryByText("0 B")).toBeNull();
  expect(
    within(panel.container).getByRole("img", { name: "old.png" }),
  ).toBeInTheDocument();
});
