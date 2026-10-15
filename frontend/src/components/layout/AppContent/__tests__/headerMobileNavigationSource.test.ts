import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const source = readFileSync(new URL("../Header.tsx", import.meta.url), "utf8");

test("mobile sidebar opener is available before the chat-only header content", () => {
  const opener = source.indexOf("setMobileSidebarOpen(true);", source.indexOf("<header"));
  expect(opener).toBeGreaterThan(-1);
  expect(opener).toBeLessThan(source.indexOf('activeTab === "chat" ?', opener));
  expect(source.slice(opener, source.indexOf("</button>", opener))).toContain(
    'aria-label={t("sidebar.expandSidebar")}',
  );
});

test("panel history back button is hidden on mobile", () => {
  expect(source).toContain("onBack={() => navigate(-1)}");
  const navigation = readFileSync(
    new URL("../../../common/PageNavigationBar.tsx", import.meta.url), "utf8",
  );
  expect(navigation).toContain('className="hidden sm:flex"');
});
