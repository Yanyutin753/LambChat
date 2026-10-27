/** @vitest-environment jsdom */

import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import {
  SessionImageGalleryProvider,
  useSessionImageGallery,
} from "../sessionImageGallery";
import { useImagePreviewFallback } from "../items/imagePreviewFallback";

// 外链地址：不命中私有图片代理前缀，jsdom 下不会触发 fetch
const SIBLINGS = [
  { src: "https://cdn.example.com/a.png", alt: "a.png" },
  { src: "https://cdn.example.com/b.png", alt: "b.png" },
  { src: "https://cdn.example.com/c.png", alt: "c.png" },
];

const NEXT = /next|下一/i;
const PREVIOUS = /previous|上一/i;

function GalleryOpener({ siblings }: { siblings?: typeof SIBLINGS }) {
  const gallery = useSessionImageGallery();
  return (
    <button
      type="button"
      onClick={() =>
        gallery?.openImage(SIBLINGS[0].src, SIBLINGS[0].alt, { siblings })
      }
    >
      open
    </button>
  );
}

test("session gallery pages within a card's siblings when it has not collected them", () => {
  render(
    <SessionImageGalleryProvider messages={[]}>
      <GalleryOpener siblings={SIBLINGS} />
    </SessionImageGalleryProvider>,
  );

  fireEvent.click(screen.getByRole("button", { name: "open" }));

  expect(screen.getByRole("dialog", { name: "a.png" })).toBeInTheDocument();
  expect(screen.getByText("1 / 3")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: PREVIOUS })).toBeNull();

  fireEvent.click(screen.getByRole("button", { name: NEXT }));

  expect(screen.getByRole("dialog", { name: "b.png" })).toBeInTheDocument();
  expect(screen.getByText("2 / 3")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: PREVIOUS })).toBeInTheDocument();
});

test("session gallery keeps the single-image lightbox when no siblings are given", () => {
  render(
    <SessionImageGalleryProvider messages={[]}>
      <GalleryOpener />
    </SessionImageGalleryProvider>,
  );

  fireEvent.click(screen.getByRole("button", { name: "open" }));

  expect(screen.getByRole("dialog", { name: "a.png" })).toBeInTheDocument();
  expect(screen.queryByText(/^\d+ \/ \d+$/)).toBeNull();
  expect(screen.queryByRole("button", { name: NEXT })).toBeNull();
});

function FallbackCard() {
  const { openImage, viewer } = useImagePreviewFallback(SIBLINGS);
  return (
    <>
      <button
        type="button"
        onClick={() => openImage(SIBLINGS[1].src, SIBLINGS[1].alt)}
      >
        open
      </button>
      {viewer}
    </>
  );
}

test("useImagePreviewFallback pages through siblings without a session gallery", () => {
  render(<FallbackCard />);

  fireEvent.click(screen.getByRole("button", { name: "open" }));

  expect(screen.getByRole("dialog", { name: "b.png" })).toBeInTheDocument();
  expect(screen.getByText("2 / 3")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: PREVIOUS }));

  expect(screen.getByRole("dialog", { name: "a.png" })).toBeInTheDocument();
  expect(screen.getByText("1 / 3")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: PREVIOUS })).toBeNull();
});
