import { LanguagePreferenceProvider } from "../../../hooks/useLanguagePreference";
/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { I18nextProvider } from "react-i18next";
import appI18n from "../../../i18n";
import { LanguageToggle } from "../LanguageToggle";
const api = vi.hoisted(() => ({
  user: undefined as { id: string } | undefined,
  write: vi.fn(),
}));
vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => ({ user: api.user }),
}));
vi.mock("../../../services/api", () => ({
  authApi: { updateMetadata: api.write },
}));
beforeEach(() => {
  api.user = undefined;
  api.write.mockReset().mockResolvedValue({});
  localStorage.clear();
});
afterEach(cleanup);
function toggle(sync = true) {
  const i18n = appI18n.cloneInstance({ lng: "zh-CN" });
  const changed = vi.spyOn(i18n, "changeLanguage");
  render(
    <I18nextProvider i18n={i18n}>
      <LanguagePreferenceProvider>
        <LanguageToggle sync={sync} />
      </LanguagePreferenceProvider>
    </I18nextProvider>,
  );
  return { i18n, changed };
}
test("guest language selection stays local, exposes selection and returns focus", async () => {
  const { i18n } = toggle();
  const trigger = screen.getByRole("button", { name: "语言" });
  fireEvent.click(trigger);
  expect(screen.getByRole("menuitemradio", { name: "中文" })).toHaveAttribute(
    "aria-checked",
    "true",
  );
  fireEvent.click(screen.getByRole("menuitemradio", { name: "English" }));
  await waitFor(() => expect(i18n.language).toBe("en"));
  expect(api.write).not.toHaveBeenCalled();
  expect(trigger).toHaveFocus();
  expect(localStorage.getItem("language")).toBe("en");
});
test("failed language sync keeps the local choice and retries the exact request once", async () => {
  api.user = { id: "first" };
  let reject!: (reason: Error) => void;
  api.write.mockReturnValueOnce(
    new Promise((_resolve, no) => {
      reject = no;
    }),
  );
  const { i18n, changed } = toggle();
  fireEvent.click(screen.getByRole("button", { name: "语言" }));
  fireEvent.click(screen.getByRole("menuitemradio", { name: "English" }));
  await waitFor(() =>
    expect(api.write).toHaveBeenCalledWith({ language: "en" }),
  );
  expect(screen.getByRole("button", { name: "Language" })).toHaveAttribute(
    "aria-busy",
    "true",
  );
  await act(async () => reject(new Error("fixture failure")));
  fireEvent.click(screen.getByRole("button", { name: "Language" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "Retry: Language" }));
  await waitFor(() => expect(api.write).toHaveBeenCalledTimes(2));
  expect(api.write).toHaveBeenLastCalledWith({ language: "en" });
  expect(changed).toHaveBeenCalledTimes(1);
  expect(i18n.language).toBe("en");
});

test("public shared language controls never write authenticated preferences", async () => {
  api.user = { id: "first" };
  const { i18n } = toggle(false);
  fireEvent.click(screen.getByRole("button", { name: "语言" }));
  fireEvent.click(screen.getByRole("menuitemradio", { name: "English" }));
  await waitFor(() => expect(i18n.language).toBe("en"));
  expect(api.write).not.toHaveBeenCalled();
});
test("language menus support arrow navigation and Escape focus return", () => {
  toggle();
  const trigger = screen.getByRole("button", { name: "语言" });
  fireEvent.click(trigger);
  expect(screen.getByRole("menuitemradio", { name: "English" })).toHaveFocus();
  fireEvent.keyDown(screen.getByRole("menu", { name: "语言" }), {
    key: "ArrowDown",
  });
  expect(screen.getByRole("menuitemradio", { name: "中文" })).toHaveFocus();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("menu")).toBeNull();
  expect(trigger).toHaveFocus();
});
