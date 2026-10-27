import { resolveImageListNavigation } from "../imageListNavigation";

const IMAGES = [
  { src: "/a.png", alt: "a.png" },
  { src: "/b.png", alt: "b.png" },
  { src: "/c.png", alt: "c.png" },
];

test("resolves neighbours and position for an image inside the list", () => {
  const nav = resolveImageListNavigation(IMAGES, "/b.png");

  expect(nav.index).toBe(1);
  expect(nav.current).toBe(IMAGES[1]);
  expect(nav.previous).toBe(IMAGES[0]);
  expect(nav.next).toBe(IMAGES[2]);
  expect(nav.positionLabel).toBe("2 / 3");
});

test("stops at the first and last image", () => {
  expect(resolveImageListNavigation(IMAGES, "/a.png").previous).toBeNull();
  expect(resolveImageListNavigation(IMAGES, "/a.png").next).toBe(IMAGES[1]);
  expect(resolveImageListNavigation(IMAGES, "/c.png").next).toBeNull();
  expect(resolveImageListNavigation(IMAGES, "/c.png").positionLabel).toBe(
    "3 / 3",
  );
});

test("reports an unknown image without any navigation", () => {
  const nav = resolveImageListNavigation(IMAGES, "/missing.png");

  expect(nav.index).toBe(-1);
  expect(nav.current).toBeNull();
  expect(nav.previous).toBeNull();
  expect(nav.next).toBeNull();
  expect(nav.positionLabel).toBeUndefined();
});

test("omits the position label for a single image and for no image", () => {
  expect(
    resolveImageListNavigation([IMAGES[0]], "/a.png").positionLabel,
  ).toBeUndefined();
  expect(resolveImageListNavigation(IMAGES, null).index).toBe(-1);
  expect(resolveImageListNavigation([], "/a.png").current).toBeNull();
});
