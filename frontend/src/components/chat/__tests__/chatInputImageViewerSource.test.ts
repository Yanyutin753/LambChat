import { readFileSync } from "node:fs";

/**
 * 输入框里选了多张图片时，预览灯箱要能在这些附件间左右切换。
 */
test("composer image viewer pages through the attached images", () => {
  const layerSource = readFileSync(
    new URL("../ChatInputDialogLayer.tsx", import.meta.url),
    "utf8",
  );
  const inputSource = readFileSync(
    new URL("../ChatInput.tsx", import.meta.url),
    "utf8",
  );

  expect(layerSource).toMatch(/resolveImageListNavigation/);
  expect(layerSource).toMatch(/onPrevious=/);
  expect(layerSource).toMatch(/onNext=/);
  expect(layerSource).toMatch(/positionLabel=/);

  expect(inputSource).toMatch(/imageViewerAttachments=\{visibleAttachments\}/);
  expect(inputSource).toMatch(/onImageViewerChange=\{/);
});
