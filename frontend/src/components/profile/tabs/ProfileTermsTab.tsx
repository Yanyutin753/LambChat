import { useTranslation, Trans } from "react-i18next";
import { Scale } from "lucide-react";

const TERMS_LINK =
  "https://www.gov.cn/zhengce/zhengceku/202307/content_6891752.htm";

export function ProfileTermsTab() {
  const { t } = useTranslation();

  return (
    <div className="rounded-2xl bg-stone-50 dark:bg-stone-700/40 p-4 border border-stone-200/60 dark:border-stone-600/40">
      <div className="flex items-center gap-2 mb-3">
        <Scale size={15} className="text-amber-500 dark:text-amber-400" />
        <h3 className="text-xs font-semibold uppercase tracking-wide text-stone-400 dark:text-stone-500">
          {t("profile.termsTab")}
        </h3>
      </div>

      <div className="text-sm text-stone-700 dark:text-stone-200 w-full flex flex-col space-y-4">
        <div className="space-y-3">
          <div className="w-full text-center text-lg">
            <b>{t("profile.termsTitle")}</b>
          </div>

          <ul
            className="text-xs text-stone-700 dark:text-stone-200 space-y-4 list-disc pl-4"
            style={{ textAlign: "justify" }}
          >
            <li>
              <Trans
                i18nKey="profile.termsItem1"
                components={{
                  a: (
                    <a
                      href={TERMS_LINK}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-amber-600 dark:text-amber-400 hover:underline"
                    />
                  ),
                }}
              />
            </li>
            <li>{t("profile.termsItem2")}</li>
            <li>
              <Trans
                i18nKey="profile.termsItem3"
                components={{
                  a: (
                    <a
                      href={TERMS_LINK}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-amber-600 dark:text-amber-400 hover:underline"
                    />
                  ),
                  strong: <strong />,
                }}
              />
            </li>
            <li>
              <strong>{t("profile.termsItem4")}</strong>
            </li>
            <li>
              <strong>{t("profile.termsItem5")}</strong>
            </li>
            <li>
              <strong>{t("profile.termsItem6")}</strong>
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}
