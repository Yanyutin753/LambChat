/** @vitest-environment jsdom */

import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { ImageWithSkeleton } from "../ImageWithSkeleton";

const FULL_SRC = "https://app.example/api/upload/file/abc/hero.jpg";
const THUMB_SRC = "https://app.example/api/upload/file/abc/hero.jpg?thumb=1";

test("auto-height inline images reserve skeleton space until loaded", () => {
  const { container } = render(
    <ImageWithSkeleton
      src="https://app.example/placeholder-test.png"
      alt="placeholder"
      inline
      aspectRatio="4 / 3"
      className="w-full h-auto"
    />,
  );
  const skeleton = container.querySelector(".skeleton-line") as HTMLElement;
  const img = screen.getByAltText("placeholder");
  expect(skeleton).toHaveClass("absolute", "inset-0");
  expect(skeleton.previousElementSibling).toHaveStyle({ aspectRatio: "4 / 3" });
  expect(img).toHaveStyle({ position: "absolute" });

  fireEvent.load(img);
  expect(container.querySelector(".skeleton-line")).toBeNull();
  expect(img.style.position).toBe("");
});

test.each([false, true])("skeleton covers the complete image container in inline=%s mode", (inline) => {
  const { container } = render(<ImageWithSkeleton src={`https://example.test/fill-${inline}.png`} inline={inline} className="h-24 w-full object-contain" />);
  expect(container.querySelector(".skeleton-line")).toHaveClass("absolute", "inset-0");
  expect(container.querySelector(".image-with-skeleton")).toHaveAttribute("aria-busy", "true");
  fireEvent.load(container.querySelector("img")!);
  expect(container.querySelector(".skeleton-line")).toBeNull();
  expect(container.querySelector(".image-with-skeleton")).toHaveAttribute("aria-busy", "false");
});

test.each([false, true])(
  "clickable image is a native preview button in inline=%s mode, including its error fallback",
  (inline) => {
    const preview = vi.fn();
    render(
      <ImageWithSkeleton
        src={FULL_SRC}
        alt="hero"
        onClick={preview}
        inline={inline}
      />,
    );
    const button = screen.getByRole("button", { name: "hero", exact: true });
    expect(button.tagName).toBe("BUTTON");
    expect(button).toHaveAttribute("type", "button");
    fireEvent.click(button);
    expect(preview).toHaveBeenCalledOnce();
    fireEvent.error(screen.getByAltText("hero"));
    fireEvent.click(button);
    expect(preview).toHaveBeenCalledTimes(2);
  },
);

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
