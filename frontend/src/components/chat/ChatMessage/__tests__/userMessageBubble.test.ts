import { getUserMessageActionButtonVisibilityClass } from "../userMessageBubbleState";

test("keeps user message action buttons visible for the latest message", () => {
  const className = getUserMessageActionButtonVisibilityClass(true);

  expect(className.includes("opacity-0")).toBe(false);
  expect(className.includes("group-hover:opacity-100")).toBe(false);
});

test("hides older user message action buttons until hover", () => {
  const className = getUserMessageActionButtonVisibilityClass(false);

  expect(className.includes("opacity-0")).toBe(true);
  expect(className.includes("group-hover:opacity-100")).toBe(true);
});
