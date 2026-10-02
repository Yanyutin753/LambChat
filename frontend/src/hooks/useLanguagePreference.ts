import {
  createContext,
  createElement,
  useContext,
  type ReactNode,
} from "react";
import { useTranslation } from "react-i18next";
import { authApi } from "../services/api";
import { useAuth } from "./useAuth";
import {
  usePreferenceWrites,
  type PreferenceWriteState,
} from "./usePreferenceWrites";

type LanguagePreference = {
  languageState: PreferenceWriteState | undefined;
  selectLanguage: (language: string, sync?: boolean) => boolean;
  retryLanguage: () => void;
};
const LanguagePreferenceContext = createContext<LanguagePreference | null>(
  null,
);

/** One account-owned write shared by the header, profile and public controls. */
export function LanguagePreferenceProvider({
  children,
}: {
  children: ReactNode;
}) {
  const { i18n } = useTranslation();
  const { user } = useAuth();
  const { states, save, retry } = usePreferenceWrites(user?.id);
  const selectLanguage = (language: string, sync = true) => {
    if (
      sync &&
      user?.id &&
      !save("language", () => authApi.updateMetadata({ language }))
    )
      return false;
    void i18n.changeLanguage(language);
    localStorage.setItem("language", language);
    return true;
  };
  return createElement(
    LanguagePreferenceContext.Provider,
    {
      value: {
        languageState: states.language,
        selectLanguage,
        retryLanguage: () => retry("language"),
      },
    },
    children,
  );
}

export function useLanguagePreference(sync = true) {
  const preference = useContext(LanguagePreferenceContext);
  if (!preference)
    throw new Error(
      "useLanguagePreference requires LanguagePreferenceProvider",
    );
  return {
    languageState: sync ? preference.languageState : undefined,
    selectLanguage: (language: string) =>
      preference.selectLanguage(language, sync),
    retryLanguage: preference.retryLanguage,
  };
}
