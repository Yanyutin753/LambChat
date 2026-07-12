import { readFileSync } from "node:fs";
import { join } from "node:path";

const shareDialogSource = readFileSync(
  join(import.meta.dirname, "../ShareDialog.tsx"),
  "utf8",
);

const enLocale = readFileSync(
  join(import.meta.dirname, "../../../i18n/locales/en.json"),
  "utf8",
);

const zhLocale = readFileSync(
  join(import.meta.dirname, "../../../i18n/locales/zh.json"),
  "utf8",
);

test("share dialog renders a privacy reminder before creating links", () => {
  expect(shareDialogSource).toMatch(/share\.privacyReminder/);
  expect(shareDialogSource).toMatch(/AlertTriangle/);
});

test("share privacy reminder is localized for open-source friendly copy", () => {
  expect(enLocale).toMatch(/"privacyReminder"/);
  expect(enLocale).toMatch(
    /remove personal information, secrets, contact details, account data/,
  );
  expect(zhLocale).toMatch(/"privacyReminder"/);
  expect(zhLocale).toMatch(/移除个人隐私、密钥、联系方式、账号信息/);
});
