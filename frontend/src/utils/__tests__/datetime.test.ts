import { startOfLocalDay } from "../datetime";

test("startOfLocalDay truncates to local midnight of the same day", () => {
  const afternoon = new Date(2026, 7, 30, 16, 42, 11, 512);
  const midnight = startOfLocalDay(afternoon);

  expect(midnight.getTime()).toBe(new Date(2026, 7, 30, 0, 0, 0, 0).getTime());
});

test("startOfLocalDay keeps dates already at midnight untouched", () => {
  const midnight = new Date(2026, 0, 1, 0, 0, 0, 0);
  expect(startOfLocalDay(midnight).getTime()).toBe(midnight.getTime());
});
