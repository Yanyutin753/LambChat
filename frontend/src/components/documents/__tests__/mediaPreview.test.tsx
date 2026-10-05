/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, expect, test, vi } from "vitest";
import { I18nextProvider } from "react-i18next";
import i18n, { i18nReady } from "../../../i18n";
import { useDocumentPreviewState } from "../useDocumentPreviewState";
import DocumentPreviewContent from "../DocumentPreviewContent";

beforeAll(async () => {
  await i18nReady;
  await i18n.loadLanguages(["zh"]);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
function Preview({ extension }: { extension: string }) {
  const state = useDocumentPreviewState({
    path: `sample.${extension}`,
    signedUrl: `/fixture.${extension}`,
    onClose: vi.fn(),
  });
  return <DocumentPreviewContent {...state} />;
}
test.each(["wav", "mp4"])(
  "%s preview identifies its native player without autoplay",
  async (extension) => {
    vi.stubGlobal("matchMedia", () => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    render(
      <I18nextProvider i18n={i18n.cloneInstance({ lng: "zh" })}>
        <Preview extension={extension} />
      </I18nextProvider>,
    );
    const player = await screen.findByLabelText(`sample.${extension}`);
    expect(player).toHaveAttribute("controls");
    expect(player).not.toHaveAttribute("autoplay");
    if (extension === "mp4") expect(player).toHaveAttribute("playsinline");
    expect(player.getAttribute("src")).toContain(`/fixture.${extension}`);
  },
);
