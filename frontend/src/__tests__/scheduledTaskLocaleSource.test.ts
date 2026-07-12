import en from "../i18n/locales/en.json";
import ja from "../i18n/locales/ja.json";
import ko from "../i18n/locales/ko.json";
import ru from "../i18n/locales/ru.json";
import zh from "../i18n/locales/zh.json";

test("scheduled-task Chinese UI copy does not expose placeholders", () => {
  const scheduledTask = zh.scheduledTask as Record<string, string>;

  expect(scheduledTask.conversationTasks).toBe("会话定时任务");
  expect(scheduledTask.details).toBe("详情");
  expect(scheduledTask.noConversationTasks).toBe(
    "当前会话暂无 Agent 创建的定时任务",
  );

  for (const value of Object.values(scheduledTask)) {
    expect(value).not.toMatch(/【待翻译】/);
  }
});

test("scheduled-task delete warning explains task sessions lose their entry point", () => {
  expect(zh.scheduledTask.deleteWarning).toMatch(/历史运行会话/);
  expect(zh.scheduledTask.deleteWarning).toMatch(/无法再从定时任务入口查看/);
  expect(en.scheduledTask.deleteWarning).toMatch(/past run sessions/i);
  expect(en.scheduledTask.deleteWarning).toMatch(/task entry point/i);
  expect(ja.scheduledTask.deleteWarning).toMatch(/過去の実行セッション/);
  expect(ja.scheduledTask.deleteWarning).toMatch(/タスクの入口/);
  expect(ko.scheduledTask.deleteWarning).toMatch(/이전 실행 세션/);
  expect(ko.scheduledTask.deleteWarning).toMatch(
    /작업入口|작업 입구|작업 항목/,
  );
  expect(ru.scheduledTask.deleteWarning).toMatch(/прошлые сеансы запусков/i);
  expect(ru.scheduledTask.deleteWarning).toMatch(/карточки задачи/i);
});
