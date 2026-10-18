/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import i18n from "../../../../i18n";
import { RunStatusBadge } from "../Badges";

afterEach(async () => {
  cleanup();
  await i18n.changeLanguage("zh");
});

test.each([
  ["zh", "等待确认"],
  ["en", "Awaiting input"],
  ["ja", "確認待ち"],
  ["ko", "확인 대기"],
  ["ru", "Ожидает ответа"],
])(
  "scheduled runs awaiting human input have a readable %s status",
  async (language, label) => {
    await i18n.changeLanguage(language);
    render(<RunStatusBadge status="waiting_human" />);
    expect(screen.getByText(label)).toBeVisible();
    expect(screen.queryByText("scheduledTask.waiting_human")).toBeNull();
  },
);

test("existing scheduled run statuses keep their labels beside awaiting input", async () => {
  await i18n.changeLanguage("zh");
  render(
    <>
      <RunStatusBadge status="pending" />
      <RunStatusBadge status="success" />
    </>,
  );
  expect(screen.getByText("等待中")).toBeVisible();
  expect(screen.getByText("成功")).toBeVisible();
});
