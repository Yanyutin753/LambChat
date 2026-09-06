import { readFileSync } from "node:fs";
import { join } from "node:path";

const bannerSource = readFileSync(
  join(process.cwd(), "src/components/notification/NotificationBanner.tsx"),
  "utf8",
);
const welcomeCssSource = readFileSync(
  join(process.cwd(), "src/styles/welcome.css"),
  "utf8",
);

test("notification banner root exposes a stable class for viewport-state styling", () => {
  expect(bannerSource).toMatch(
    /className="[^"]*notification-banner-root[^"]*"/,
  );
});

test("welcome page hides the pinned banner while the mobile keyboard is open", () => {
  expect(welcomeCssSource).toMatch(
    /html\[data-mobile-keyboard="true"\]\s*\.notification-banner-root\s*\{\s*display:\s*none;\s*\}/,
  );
});
