import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import { renderToStaticMarkup } from "react-dom/server";
import { PieChart } from "lucide-react";
import { DistributionList } from "../RankingCards";
import zh from "../../../../i18n/locales/zh.json";
import en from "../../../../i18n/locales/en.json";
import ja from "../../../../i18n/locales/ja.json";
import ko from "../../../../i18n/locales/ko.json";
import ru from "../../../../i18n/locales/ru.json";

const resources = { zh, en, ja, ko, ru };

test.each([
  ["zh", "对话", "定时任务", "手动触发"],
  ["en", "Chat", "Scheduled task", "Manual trigger"],
  ["ja", "チャット", "定期タスク", "手動実行"],
  ["ko", "대화", "예약 작업", "수동 실행"],
  ["ru", "Чат", "Задача по расписанию", "Ручной запуск"],
] as const)(
  "distribution names follow %s and preserve unknown labels",
  async (lng, chat, scheduled, manual) => {
    const i18n = createInstance();
    await i18n.init({
      lng,
      resources: Object.fromEntries(
        Object.entries(resources).map(([locale, translation]) => [
          locale,
          { translation },
        ]),
      ),
    });
    function render(prefix: string, ids: string[]) {
      return renderToStaticMarkup(
        <I18nextProvider i18n={i18n}>
          <DistributionList
            title="Distribution"
            icon={PieChart}
            total={10}
            emptyLabel="Empty"
            nameKeyPrefix={prefix}
            items={ids.map((id) => ({
              id,
              name: id === "custom" ? "Custom source" : id,
              requests: 1,
              tokens: 10,
              duration: 1,
              input_tokens: 6,
              cache_creation_tokens: 0,
              cache_read_tokens: 0,
              cache_read_share: 0,
              zero_cache_requests: 1,
            }))}
          />
        </I18nextProvider>,
      );
    }
    const sources = render("usage.sources", [
      "chat",
      "scheduled_task",
      "auxiliary",
      "custom",
    ]);
    expect(sources).toContain(chat);
    expect(sources).toContain(scheduled);
    expect(sources).toContain(resources[lng].usage.sources.auxiliary);
    expect(sources).toContain("Custom source");
    expect(sources).not.toContain("scheduled_task");
    expect(render("usage.triggers", ["manual"])).toContain(manual);
  },
);
