import { expect, test, vi } from "vitest";
import { readFileSync } from "node:fs";
const { setLanguage } = vi.hoisted(() => ({ setLanguage: vi.fn().mockResolvedValue(undefined) }));
vi.mock("../../services/capacitor/localDevice", () => ({
  isAndroidLocalDevice: () => true,
  LocalDevice: { setLanguage },
}));
import i18n, { i18nReady } from "../index";

test("app language changes are forwarded to native phone controls", async () => {
  await i18nReady;
  for (const language of ["zh", "ja", "ko", "ru", "en"]) {
    await i18n.changeLanguage(language);
    expect(setLanguage).toHaveBeenLastCalledWith({ language });
  }
});

test("all native local-device strings have five-language coverage", () => {
  const keys = (suffix: string) => [...readFileSync(`android/app/src/main/res/values${suffix}/strings_local_device.xml`, "utf8").matchAll(/<string name="([^"]+)"/g)].map(match => match[1]).sort();
  for (const language of ["zh", "ja", "ko", "ru"]) expect(keys(`-${language}`)).toEqual(keys(""));
});
