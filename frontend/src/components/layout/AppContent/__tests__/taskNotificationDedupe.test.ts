import {
  clearTaskNotificationDedupe,
  hasTaskNotified,
  markTaskNotified,
} from "../taskNotificationDedupe";

test("unmarked keys are considered unnotified", () => {
  clearTaskNotificationDedupe();
  expect(hasTaskNotified("task:run-1:completed")).toBe(false);
});

test("marks a key as notified so later deliveries can dedupe", () => {
  clearTaskNotificationDedupe();
  markTaskNotified("task:run-1:completed");
  expect(hasTaskNotified("task:run-1:completed")).toBe(true);
  expect(hasTaskNotified("task:run-1:failed")).toBe(false);
});
