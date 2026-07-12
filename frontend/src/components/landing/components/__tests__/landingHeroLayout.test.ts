import { getHeroSectionClassName } from "../landingHeroLayout.ts";

test("keeps the landing hero centered and balanced on mobile", () => {
  const className = getHeroSectionClassName();

  expect(className.includes("items-center")).toBe(true);
  expect(className.includes("justify-center")).toBe(true);
  expect(className.includes("min-h-[100dvh]")).toBe(true);
  expect(className.includes("pt-24 pb-16")).toBe(false);
  expect(
    className.includes("pt-[calc(5rem+var(--app-safe-area-top,0px))]"),
  ).toBe(true);
  expect(className.includes("pb-20")).toBe(true);
});
