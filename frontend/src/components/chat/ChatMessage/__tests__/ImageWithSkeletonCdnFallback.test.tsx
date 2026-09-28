/** @vitest-environment jsdom */

import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { ImageWithSkeleton } from "../ImageWithSkeleton";

const NPM_MIRROR =
  "https://registry.npmmirror.com/@lobehub/fluent-emoji-anim-2/latest/files/assets/1f4c4.webp";
const JSDELIVR =
  "https://cdn.jsdelivr.net/npm/@lobehub/fluent-emoji-anim-2@latest/assets/1f4c4.webp";
const UNPKG =
  "https://unpkg.com/@lobehub/fluent-emoji-anim-2@latest/assets/1f4c4.webp";

function currentImgSrc(): string {
  const img = screen.getByAltText("page") as HTMLImageElement;
  return img.getAttribute("src") ?? "";
}

test("retries emoji assets on alternative CDNs before showing the error state", () => {
  render(<ImageWithSkeleton src={NPM_MIRROR} alt="page" />);

  // npmmirror 失败 → jsdelivr
  fireEvent.error(screen.getByAltText("page"));
  expect(currentImgSrc()).toBe(JSDELIVR);

  // jsdelivr 也失败 → unpkg
  fireEvent.error(screen.getByAltText("page"));
  expect(currentImgSrc()).toBe(UNPKG);

  // 全部失败才进入错误态
  fireEvent.error(screen.getByAltText("page"));
  expect(screen.queryByAltText("page")).not.toBeInTheDocument();
  expect(screen.getByText("page")).toBeInTheDocument();
});

test("non-emoji urls fail straight into the error state", () => {
  render(<ImageWithSkeleton src="https://app.example/api/files/a.jpg" alt="hero" />);
  fireEvent.error(screen.getByAltText("hero"));
  expect(screen.queryByAltText("hero")).not.toBeInTheDocument();
  expect(screen.getByText("hero")).toBeInTheDocument();
});

test("reports onError only after every CDN alternative failed", () => {
  let reported = 0;
  render(
    <ImageWithSkeleton
      src={NPM_MIRROR}
      alt="page"
      onError={() => {
        reported += 1;
      }}
    />,
  );
  const img = screen.getByAltText("page");

  fireEvent.error(img);
  fireEvent.error(img);
  expect(reported).toBe(0);

  fireEvent.error(img);
  expect(reported).toBe(1);
});
