import { readFileSync } from "node:fs";

const source = readFileSync(
  new URL("../ResponsiveSection.tsx", import.meta.url),
  "utf8",
);

test("centers responsive screenshots at their full aspect ratio", () => {
  expect(source).toMatch(
    /<img[\s\S]*?className="mx-auto w-auto max-w-full h-80 sm:h-\[28rem\] lg:h-\[32rem\] object-contain rounded-lg"/,
  );
  expect(source).not.toMatch(/<ImageWithSkeleton[\s\S]*?\binline\b/);
});
