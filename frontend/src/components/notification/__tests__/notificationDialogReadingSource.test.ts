import { readFileSync } from "node:fs";
import { join } from "node:path";

const source = readFileSync(
  join(process.cwd(), "src/components/notification/NotificationDialog.tsx"),
  "utf8",
);

test("announcement body preserves paragraphs and wraps long links", () => {
  expect(source).toMatch(/whitespace-pre-wrap/);
  expect(source).toMatch(/\[overflow-wrap:anywhere\]/);
  expect(source).not.toMatch(/line-clamp/);
});

test("announcement list can shrink and scroll below a fixed header", () => {
  expect(source).toMatch(/min-h-0[^"\n]*overflow-y-auto/);
  expect(source).toMatch(/className="shrink-0"/);
});

test("announcement header and empty state use existing lamb artwork", () => {
  expect(source).toMatch(/scene="notification"/);
  expect(source).toMatch(/scene="message"/);
});
