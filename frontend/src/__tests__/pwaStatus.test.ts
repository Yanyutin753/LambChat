import {
  getInitialOnlineStatus,
  shouldShowRestoredConnectionToast,
} from "../pwaStatus.ts";

test("treats missing navigator online state as online by default", () => {
  expect(getInitialOnlineStatus(undefined)).toBe(true);
  expect(getInitialOnlineStatus({})).toBe(true);
});

test("reads explicit browser online state", () => {
  expect(getInitialOnlineStatus({ onLine: true })).toBe(true);
  expect(getInitialOnlineStatus({ onLine: false })).toBe(false);
});

test("shows restored connection feedback only after an offline state", () => {
  expect(
    shouldShowRestoredConnectionToast({
      wasOnline: false,
      isOnline: true,
    }),
  ).toBe(true);
  expect(
    shouldShowRestoredConnectionToast({
      wasOnline: true,
      isOnline: true,
    }),
  ).toBe(false);
  expect(
    shouldShowRestoredConnectionToast({
      wasOnline: false,
      isOnline: false,
    }),
  ).toBe(false);
});
