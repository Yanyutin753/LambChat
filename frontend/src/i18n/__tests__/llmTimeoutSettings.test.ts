import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = dirname(fileURLToPath(import.meta.url));
const localesDir = resolve(currentDir, "../locales");
const locales = ["en", "zh", "ja", "ko", "ru"];

test("all locales describe the split LLM timeout settings", () => {
  for (const locale of locales) {
    const messages = JSON.parse(
      readFileSync(resolve(localesDir, `${locale}.json`), "utf8"),
    ) as { settingDesc: Record<string, string> };

    expect(messages.settingDesc.LLM_REQUEST_TIMEOUT).toBeTruthy();
    expect(messages.settingDesc.LLM_FIRST_EVENT_TIMEOUT).toBeTruthy();
    expect(messages.settingDesc.LLM_STREAM_IDLE_TIMEOUT).toBeTruthy();
    expect(messages.settingDesc.LLM_REQUEST_TIMEOUT).not.toMatch(
      /first streaming event|流式首事件|最初のストリーミングイベント|첫 스트리밍 이벤트|первого события потока/i,
    );
  }
});
