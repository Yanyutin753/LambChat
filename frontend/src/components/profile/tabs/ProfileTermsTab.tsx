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
    <div className="profile-terms">
      <div>
        <span className="text-12 leading-relaxed text-theme-text-secondary dark:text-stone-300">
          <Trans
            i18nKey="profile.termsItem1"
            components={{ a: regulationLink }}
          />
        </span>
      </div>

      <div>
        <span className="text-12 leading-relaxed text-theme-text-secondary dark:text-stone-300">
          <Trans
            i18nKey="profile.termsItem3"
            components={{ a: regulationLink, strong: <strong /> }}
          />
        </span>
      </div>

      <div className="space-y-4">
        {(["termsItem4", "termsItem5", "termsItem6"] as const).map((key) => (
          <div key={key}>
            <span className="text-12 leading-relaxed text-theme-text-secondary dark:text-stone-300">
              {t(`profile.${key}`)}
            </span>
          </div>
        ))}
      </div>

      <p className="text-10 text-theme-text-tertiary dark:text-stone-500 text-center pt-1">
        {t("auth.termsHint")}
      </p>
    </div>
  );
}
