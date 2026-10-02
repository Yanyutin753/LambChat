/** @vitest-environment jsdom */
import { readFileSync } from "node:fs";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { I18nextProvider } from "react-i18next";
import i18n from "../../../../i18n";
import PptPreview from "../PptPreview";

const bytes = readFileSync("scripts/fixtures/preview-text-slides.pptx");
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test.each([
  ["zh", "幻灯片"],
  ["en", "Slide"],
  ["ja", "スライド"],
  ["ko", "슬라이드"],
  ["ru", "Слайд"],
])(
  "%s text fallback identifies each recovered slide",
  async (language, label) => {
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        disconnect() {}
      },
    );
    const locale = i18n.cloneInstance({ lng: language });
    render(
      <I18nextProvider i18n={locale}>
        <PptPreview
          url="/sample.pptx"
          arrayBuffer={new Uint8Array(bytes).buffer}
          fileName="sample.pptx"
          t={locale.t}
        />
      </I18nextProvider>,
    );
    expect(
      await screen.findByRole("heading", { name: `${label} 1` }),
    ).toBeVisible();
    expect(screen.getByRole("heading", { name: `${label} 2` })).toBeVisible();
    expect(screen.getByText(/Final review\. Check keyboard/)).toBeVisible();
    expect(
      screen.queryByRole("button", { name: locale.t("imageViewer.zoomIn") }),
    ).toBeNull();
  },
);
