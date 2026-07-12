/** @vitest-environment jsdom */
import { renderToStaticMarkup } from "react-dom/server";

import { ActiveGoalBar } from "../ActiveGoalBar.tsx";

test("renders final goal runtime from lifecycle timestamps", () => {
  const html = renderToStaticMarkup(
    <ActiveGoalBar
      goal={{
        objective: "finish docs",
        started_at: "2026-05-30T08:00:00.000Z",
        ended_at: "2026-05-30T08:02:03.000Z",
      }}
      durationLabel="运行"
    />,
  );

  expect(html).toMatch(/finish docs/);
  expect(html).toMatch(/运行 02:03/);
});

test("embedded mode omits standalone border/background", () => {
  const html = renderToStaticMarkup(
    <ActiveGoalBar
      goal={{
        objective: "embedded goal",
        started_at: "2026-05-30T08:00:00.000Z",
        ended_at: "2026-05-30T08:01:00.000Z",
      }}
      durationLabel="运行"
      embedded
    />,
  );

  // Embedded should NOT have the standalone emerald border/bg classes
  expect(!html.includes("border-emerald")).toBeTruthy();
  expect(!html.includes("bg-emerald")).toBeTruthy();
  // Should still show the objective
  expect(html).toMatch(/embedded goal/);
});

test("returns null when goal is null", () => {
  const html = renderToStaticMarkup(<ActiveGoalBar goal={null} />);
  expect(html).toBe("");
});
