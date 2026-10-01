import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const source = readFileSync(new URL("../Header.tsx", import.meta.url), "utf8");

test("mobile sidebar opener is available before the chat-only header content", () => {
  const opener = source.indexOf("onClick={() => setMobileSidebarOpen(true)}");
  expect(opener).toBeGreaterThan(-1);
  expect(opener).toBeLessThan(source.indexOf('activeTab === "chat" ?'));
  expect(source.slice(opener, source.indexOf("</button>", opener))).toContain(
    'aria-label={t("sidebar.expandSidebar")}',
  );
});

test("panel history back button is hidden on mobile", () => {
  const back = source.indexOf("onClick={() => navigate(-1)}");
  expect(back).toBeGreaterThan(-1);
  expect(source.slice(back, source.indexOf("</button>", back))).toMatch(
    /className="hidden sm:flex /,
  );
});
