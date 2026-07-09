import { selectNotificationDeliveryMode } from "../browserNotificationDelivery.ts";

test("uses service worker notifications on mobile when available", () => {
  expect(
    selectNotificationDeliveryMode({
      isMobile: true,
      permission: "granted",
      hasNotificationApi: true,
      hasServiceWorkerNotification: true,
    }),
  ).toBe("service-worker");
});

test("does not fall back to the Notification constructor on mobile", () => {
  expect(
    selectNotificationDeliveryMode({
      isMobile: true,
      permission: "granted",
      hasNotificationApi: true,
      hasServiceWorkerNotification: false,
    }),
  ).toBe("none");
});

test("keeps the constructor fallback for desktop browsers", () => {
  expect(
    selectNotificationDeliveryMode({
      isMobile: false,
      permission: "granted",
      hasNotificationApi: true,
      hasServiceWorkerNotification: false,
    }),
  ).toBe("constructor");
});

test("does not deliver notifications before permission is granted", () => {
  expect(
    selectNotificationDeliveryMode({
      isMobile: false,
      permission: "default",
      hasNotificationApi: true,
      hasServiceWorkerNotification: true,
    }),
  ).toBe("none");
});
