import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

test("subagent messages and waits use their dedicated item", () => {
  const renderer = readFileSync(
    resolve(here, "../../MessagePartRenderer.tsx"),
    "utf8",
  );
  const exports = readFileSync(resolve(here, "../../ToolCallItem.tsx"), "utf8");
  expect(renderer).toMatch(/part\.name === "send_subagent_message"/);
  expect(renderer).toMatch(/part\.name === "wait_subagent"/);
  expect(renderer).toMatch(/part\.name === "send_parent_message"/);
  expect(renderer).toMatch(/<SubagentControlItem/);
  expect(exports).toMatch(/export \{ SubagentControlItem \}/);
});

test("subagent control wording covers both actions and all result states in every locale", () => {
  const keys = [
    "toolSendSubagentMessage",
    "toolWaitSubagent",
    "toolSendParentMessage",
    "toolReceiveSubagentMessage",
    "toolSubagentRunning",
    "toolSubagentMessageQueued",
    "toolSubagentCompleted",
    "toolSubagentWaitingHuman",
    "toolSubagentFailed",
    "subagentMessage",
  ];
  for (const locale of ["zh", "en", "ja", "ko", "ru"]) {
    const data = JSON.parse(
      readFileSync(
        resolve(here, `../../../../../i18n/locales/${locale}.json`),
        "utf8",
      ),
    );
    for (const key of keys) {
      expect(data.chat.message[key], `${locale}: ${key}`).toEqual(
        expect.any(String),
      );
      expect(data.chat.message[key].trim()).not.toBe("");
    }
  }
});
