import { useTranslation, Trans } from "react-i18next";

const TERMS_LINK =
  "https://www.gov.cn/zhengce/zhengceku/202307/content_6891752.htm";

const regulationLink = (
  <a
    href={TERMS_LINK}
    target="_blank"
    rel="noopener noreferrer"
    className="text-amber-600 dark:text-amber-400 hover:underline"
  />
);

export function ProfileTermsTab() {
  const { t } = useTranslation();

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold font-serif text-stone-800 dark:text-stone-100">
        {t("profile.termsTitle")}
      </h3>

      <div className="p-3 rounded-lg bg-amber-50/50 dark:bg-amber-500/[0.04]">
        <span className="text-xs leading-relaxed text-stone-600 dark:text-stone-300">
          <Trans
            i18nKey="profile.termsItem1"
            components={{ a: regulationLink }}
          />
        </span>
      </div>

      <div className="p-3 rounded-lg bg-red-50/50 dark:bg-red-500/[0.04]">
        <span className="text-xs leading-relaxed text-stone-600 dark:text-stone-300">
          <Trans
            i18nKey="profile.termsItem3"
            components={{ a: regulationLink, strong: <strong /> }}
          />
        </span>
      </div>

      <div className="space-y-2">
        {(["termsItem4", "termsItem5", "termsItem6"] as const).map((key) => (
          <div
            key={key}
            className="p-2.5 rounded-lg bg-stone-50/60 dark:bg-stone-800/40"
          >
            <span className="text-xs leading-relaxed text-stone-600 dark:text-stone-300">
              {t(`profile.${key}`)}
            </span>
          </div>
        ))}
      </div>

      <p className="text-10 text-stone-400 dark:text-stone-500 text-center pt-1">
        {t("auth.termsHint")}
      </p>
    </div>
  );
}
