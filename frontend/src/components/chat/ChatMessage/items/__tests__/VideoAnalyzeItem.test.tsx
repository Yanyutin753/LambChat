/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  waitFor,
  within,
} from "@testing-library/react";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import { afterEach, expect, test, vi } from "vitest";
import zh from "../../../../../i18n/locales/zh.json";
import { resolveUploadFileUrl } from "../../../../../services/api/uploadFileUrl";
import { VideoAnalyzeItem } from "../VideoAnalyzeItem";
import {
  closeAllPersistentToolPanels,
  getPersistentToolPanelState,
} from "../persistentToolPanelState";

vi.mock(
  "../../../../../services/api/uploadFileUrl",
  async (importOriginal) => ({
    ...(await importOriginal<
      typeof import("../../../../../services/api/uploadFileUrl")
    >()),
    resolveUploadFileUrl: vi.fn(
      async () => "https://private.example/video?capability=owner",
    ),
  }),
);

const i18n = createInstance();
await i18n.init({ lng: "zh", resources: { zh: { translation: zh } } });
const source = "C:\\Users\\yangyang\\Videos\\12月5日(1).mp4";

afterEach(() => {
  cleanup();
  closeAllPersistentToolPanels();
  vi.clearAllMocks();
});

function openDetail(
  result: React.ComponentProps<typeof VideoAnalyzeItem>["result"],
  isPending = false,
) {
  const row = render(
    <I18nextProvider i18n={i18n}>
      <VideoAnalyzeItem
        args={{ video_urls: [source] }}
        result={result}
        isPending={isPending}
        success
      />
    </I18nextProvider>,
  );
  fireEvent.click(within(row.container).getByRole("button"));
  return render(
    <I18nextProvider i18n={i18n}>
      {getPersistentToolPanelState()!.children}
    </I18nextProvider>,
  );
}

test.each([false, true])(
  "plays the owned preview with the native filename (JSON=%s)",
  async (asString) => {
    const result = {
      analysis: "视频分析成功",
      videos: [
        {
          url: source,
          preview_url: "/api/upload/file/revealed_files/preview.mp4",
        },
      ],
    };
    const panel = openDetail(asString ? JSON.stringify(result) : result);
    await waitFor(() =>
      expect(panel.container.querySelector("video")?.src).toBe(
        "https://private.example/video?capability=owner",
      ),
    );
    expect(resolveUploadFileUrl).toHaveBeenCalled();
    expect(within(panel.container).getByText("12月5日(1).mp4")).toBeVisible();
    expect(within(panel.container).queryByRole("alert")).toBeNull();
  },
);

test("legacy native results keep the analysis and explain the unavailable preview", () => {
  const panel = openDetail({
    analysis: "视频分析成功",
    videos: [{ url: source }],
  });
  expect(within(panel.container).getByRole("alert")).toHaveTextContent(
    "本地视频暂无可用预览",
  );
  expect(within(panel.container).getByText("视频分析成功")).toBeVisible();
  expect(panel.container.querySelector("video")).toBeNull();
  expect(resolveUploadFileUrl).not.toHaveBeenCalled();
});

test("an analysis in progress does not ask the user to analyze again", () => {
  const panel = openDetail(undefined, true);
  expect(within(panel.container).queryByRole("alert")).toBeNull();
  expect(within(panel.container).getByText("执行中")).toBeVisible();
});
