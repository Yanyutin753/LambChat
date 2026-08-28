/** @vitest-environment jsdom */

import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { ImageWithSkeleton } from "../ImageWithSkeleton";

const FULL_SRC = "https://app.example/api/upload/file/abc/hero.jpg";
const THUMB_SRC = "https://app.example/api/upload/file/abc/hero.jpg?thumb=1";

function currentImgSrc(): string {
  const img = screen.getByAltText("hero") as HTMLImageElement;
  return img.getAttribute("src") ?? "";
}

test("renders the thumbnail URL when thumbSrc is provided", () => {
  render(<ImageWithSkeleton src={FULL_SRC} thumbSrc={THUMB_SRC} alt="hero" />);
  expect(currentImgSrc()).toBe(THUMB_SRC);
});

test("renders the original URL when no thumbSrc is provided", () => {
  render(<ImageWithSkeleton src={FULL_SRC} alt="hero" />);
  expect(currentImgSrc()).toBe(FULL_SRC);
});

test("falls back to the original once when the thumbnail fails", () => {
  render(<ImageWithSkeleton src={FULL_SRC} thumbSrc={THUMB_SRC} alt="hero" />);
  const img = screen.getByAltText("hero");

  fireEvent.error(img);
  expect(currentImgSrc()).toBe(FULL_SRC);

  // 原图也失败才进入错误态
  fireEvent.error(img);
  expect(screen.getByText("hero")).toBeInTheDocument();
  expect(screen.queryByAltText("hero")).not.toBeInTheDocument();
});

test("reports onError only after the original also fails", () => {
  let reported = 0;
  render(
    <ImageWithSkeleton
      src={FULL_SRC}
      thumbSrc={THUMB_SRC}
      alt="hero"
      onError={() => {
        reported += 1;
      }}
    />,
  );
  const img = screen.getByAltText("hero");

  fireEvent.error(img);
  expect(reported).toBe(0);

  fireEvent.error(img);
  expect(reported).toBe(1);
});
