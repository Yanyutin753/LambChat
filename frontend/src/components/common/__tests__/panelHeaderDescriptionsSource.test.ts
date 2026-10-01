import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const source = (path: string) =>
  readFileSync(new URL(path, import.meta.url), "utf8");

test("resource page headers include descriptions", () => {
  for (const [path, key] of [
    ["../../panels/ScheduledTaskPanel/index.tsx", "scheduledTask.subtitle"],
    ["../../panels/NotificationPanel.tsx", "notification.subtitle"],
    ["../../fileLibrary/components/Toolbar.tsx", "fileLibrary.subtitle"],
  ]) {
    expect(source(path)).toContain(`subtitle={t("${key}")}`);
  }
  expect(source("../../panels/AgentModelPanel/AgentModelPanel.tsx")).toMatch(
    /subtitle=/,
  );
});

test("header descriptions keep a compact two pixel title gap", () => {
  expect(source("../../../styles/panels.css")).toMatch(
    /\.panel-header__subtitle\s*\{\s*margin-top: 0\.125rem/,
  );
});
