import {
  shouldAttemptAppTaskNotification,
  shouldAttemptBrowserNotification,
  shouldSurfaceTaskNotification,
} from "../taskNotificationGuards.ts";

test("does not surface task notifications for the visible active session", () => {
  expect(
    shouldSurfaceTaskNotification({
      notificationSessionId: "session-1",
      currentSessionId: "session-1",
      visibilityState: "visible",
    }),
  ).toBe(false);
});

test("surfaces task notifications for inactive or hidden sessions", () => {
  expect(
    shouldSurfaceTaskNotification({
      notificationSessionId: "session-2",
      currentSessionId: "session-1",
      visibilityState: "visible",
    }),
  ).toBe(true);
  expect(
    shouldSurfaceTaskNotification({
      notificationSessionId: "session-1",
      currentSessionId: "session-1",
      visibilityState: "hidden",
    }),
  ).toBe(true);
});

test("attempts browser notifications only after permission is granted and the task should surface", () => {
  expect(
    shouldAttemptBrowserNotification({
      isSupported: true,
      cachedPermission: "granted",
      notificationSessionId: "session-2",
      currentSessionId: "session-1",
      visibilityState: "visible",
    }),
  ).toBe(true);
  expect(
    shouldAttemptBrowserNotification({
      isSupported: true,
      cachedPermission: "granted",
      notificationSessionId: "session-1",
      currentSessionId: "session-1",
      visibilityState: "hidden",
    }),
  ).toBe(true);
  expect(
    shouldAttemptBrowserNotification({
      isSupported: true,
      cachedPermission: "granted",
      notificationSessionId: "session-1",
      currentSessionId: "session-1",
      visibilityState: "visible",
    }),
  ).toBe(false);
  expect(
    shouldAttemptBrowserNotification({
      isSupported: true,
      cachedPermission: "default",
      notificationSessionId: "session-2",
      currentSessionId: "session-1",
      visibilityState: "visible",
    }),
  ).toBe(false);
  expect(
    shouldAttemptBrowserNotification({
      isSupported: false,
      cachedPermission: "granted",
      notificationSessionId: "session-2",
      currentSessionId: "session-1",
      visibilityState: "hidden",
    }),
  ).toBe(false);
});

test("does not attempt app task notifications for the visible active session", () => {
  expect(
    shouldAttemptAppTaskNotification({
      appRuntime: "capacitor-android",
      notificationSessionId: "session-1",
      currentSessionId: "session-1",
      visibilityState: "visible",
    }),
  ).toBe(false);
});

test("attempts app task notifications for other sessions while the native app is visible", () => {
  expect(
    shouldAttemptAppTaskNotification({
      appRuntime: "tauri",
      notificationSessionId: "session-2",
      currentSessionId: "session-1",
      visibilityState: "visible",
    }),
  ).toBe(true);
});

test("attempts app task notifications when the native app is hidden", () => {
  expect(
    shouldAttemptAppTaskNotification({
      appRuntime: "capacitor-android",
      notificationSessionId: "session-1",
      currentSessionId: "session-1",
      visibilityState: "hidden",
    }),
  ).toBe(true);
  expect(
    shouldAttemptAppTaskNotification({
      appRuntime: "tauri",
      notificationSessionId: "session-2",
      currentSessionId: "session-1",
      visibilityState: "hidden",
    }),
  ).toBe(true);
});

test("does not attempt app task notifications when native notifications are unsupported", () => {
  expect(
    shouldAttemptAppTaskNotification({
      appRuntime: "unsupported",
      notificationSessionId: "session-2",
      currentSessionId: "session-1",
      visibilityState: "hidden",
    }),
  ).toBe(false);
});
