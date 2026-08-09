import en from "../locales/en.json";
import ja from "../locales/ja.json";
import ko from "../locales/ko.json";
import ru from "../locales/ru.json";
import zh from "../locales/zh.json";

const locales = { en, ja, ko, ru, zh };

test("right panel resize label exists in every supported locale", () => {
  for (const [locale, messages] of Object.entries(locales)) {
    expect(
      messages.common.resizePanel,
      `${locale}.common.resizePanel`,
    ).toBeTruthy();
  }
});
