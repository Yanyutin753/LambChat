import { getHeroSectionClassName } from "../landingHeroLayout.ts";

test("keeps the landing hero centered and balanced on mobile", () => {
  const className = getHeroSectionClassName();

  expect(className.includes("items-center")).toBe(true);
  expect(className.includes("justify-center")).toBe(true);
  // 全屏高度扣除自绘标题栏（网页 --titlebar-inset 为 0，行为不变）
  expect(
    className.includes("min-h-[calc(100dvh-var(--titlebar-inset,0px))]"),
  ).toBe(true);
  expect(className.includes("pt-24 pb-16")).toBe(false);
  expect(
    className.includes("pt-[calc(5rem+var(--app-safe-area-top,0px))]"),
  ).toBe(true);
  expect(className.includes("pb-20")).toBe(true);
});
