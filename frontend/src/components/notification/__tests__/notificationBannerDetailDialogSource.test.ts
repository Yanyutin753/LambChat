import { readFileSync } from "node:fs";
import { join } from "node:path";
const source = readFileSync(
  join(process.cwd(), "src/components/notification/NotificationBanner.tsx"),
  "utf8",
);

test("notification banner opens a detail dialog from the compact card", () => {
  expect(source).toMatch(/selectedNotification/);
  expect(source).toMatch(/setSelectedNotification\(current\)/);
});

test("banner detail dialog shares the selector modal parent shell", () => {
  // 与 AgentModeSelector / NotificationDialog 一致：遮罩与容器走共享父组件
  expect(source).toMatch(/SelectorModalPortal/);
  expect(source).toMatch(/<SelectorModalPortal/);
  expect(source).toMatch(/<SelectorModalShell/);
  expect(source).not.toMatch(/createPortal/);
  expect(source).not.toMatch(/fixed inset-0 z-\[320\]/);
  expect(source).not.toMatch(/bg-black\/50/);
});

test("banner detail dialog keeps dialog semantics", () => {
  expect(
    readFileSync(
      new URL("../../common/ModalSurface.tsx", import.meta.url),
      "utf8",
    ),
  ).toMatch(/role="dialog"/);
  expect(
    readFileSync(
      new URL("../../common/ModalSurface.tsx", import.meta.url),
      "utf8",
    ),
  ).toMatch(/aria-modal="true"/);
  expect(source).toMatch(/aria-labelledby="notification-banner-detail-title"/);
  expect(source).toMatch(/notification-banner-detail/);
  expect(
    readFileSync(
      new URL("../../common/ModalSurface.tsx", import.meta.url),
      "utf8",
    ),
  ).toMatch(/useDialogFocus/);
  expect(
    readFileSync(
      new URL("../../common/useDialogFocus.ts", import.meta.url),
      "utf8",
    ),
  ).toMatch(/Escape/);
});

test("banner detail dialog shows publish date, not admin activation state", () => {
  // is_active 是管理端元数据，对读公告的用户无意义，不允许再泄漏到详情弹窗
  expect(source).toMatch(/created_at\.slice\(0, 10\)/);
  expect(source).not.toMatch(/is_active/);
  expect(source).not.toMatch(/notification\.active/);
  expect(source).not.toMatch(/notification\.inactive/);
});
