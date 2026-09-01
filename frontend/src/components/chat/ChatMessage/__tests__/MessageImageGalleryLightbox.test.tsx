/** @vitest-environment jsdom */

import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { MessageImageGallery } from "../MessageImageGallery";
import { SessionImageGalleryProvider } from "../sessionImageGallery";

const IMAGE = {
  id: "reveal-1",
  src: "https://app.example.com/api/upload/file/generated-images/img-1.png",
  fileName: "img-1.png",
};

test("opens a local lightbox fallback when session gallery context is absent", () => {
  // 分享页未挂 SessionImageGalleryProvider，此时点击不能是静默 no-op
  render(<MessageImageGallery images={[IMAGE]} />);

  expect(screen.getAllByAltText("img-1.png")).toHaveLength(1);

  fireEvent.click(screen.getByAltText("img-1.png"));

  // 点击后应弹出 ImageViewer 灯箱（出现第二张同 alt 的大图）
  expect(screen.getAllByAltText("img-1.png")).toHaveLength(2);
});

test("routes clicks through the session gallery provider when present", () => {
  render(
    <SessionImageGalleryProvider messages={[]}>
      <MessageImageGallery images={[IMAGE]} />
    </SessionImageGalleryProvider>,
  );

  expect(screen.getAllByAltText("img-1.png")).toHaveLength(1);

  fireEvent.click(screen.getByAltText("img-1.png"));

  expect(screen.getAllByAltText("img-1.png")).toHaveLength(2);
});
