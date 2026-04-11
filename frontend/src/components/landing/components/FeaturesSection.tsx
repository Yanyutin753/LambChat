import { useTranslation } from "react-i18next";
import { FEATURES } from "../data";
import { SectionHeading } from "./SectionHeading";

export function FeaturesSection() {
  const { t } = useTranslation();

  return (
    <section
      id="features"
      className="py-20 sm:py-28 lg:py-36 relative scroll-mt-14"
    >
      <div className="max-w-5xl lg:max-w-6xl mx-auto px-5 sm:px-6">
        <SectionHeading
          label={t("landing.sectionLabelFeatures")}
          title={t("landing.coreFeatures")}
          description={t("landing.coreFeaturesDesc")}
        />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5">
          {FEATURES.map((f, i) => (
            <div
              key={f.titleKey}
              data-reveal
              data-reveal-delay={String(Math.min(i + 1, 6))}
              className="blog-feature-card group relative rounded-2xl border border-stone-100/80 dark:border-stone-800/40 bg-white/80 dark:bg-stone-900/40 p-7 sm:p-8 transition-all duration-500 hover:-translate-y-1.5 hover:bg-white dark:hover:bg-stone-900/60"
            >
              {/* Top gradient accent */}
              <div
                className={`absolute top-0 left-7 sm:left-8 w-8 h-[2px] bg-gradient-to-r ${f.gradient} rounded-full opacity-50 group-hover:opacity-90 group-hover:w-12 transition-all duration-500`}
              />
              <div
                className={`flex items-center justify-center w-11 h-11 sm:w-12 sm:h-12 rounded-xl bg-gradient-to-br ${f.gradient} text-lg sm:text-xl mb-5 sm:mb-6 shadow-sm transition-all duration-400 group-hover:scale-110 group-hover:rotate-3 group-hover:shadow-md`}
              >
                {f.icon}
              </div>
              <h3 className="text-[15px] sm:text-base font-bold text-stone-900 dark:text-stone-100 mb-2.5 leading-snug">
                {t(`landing.${f.titleKey}`, f.titleKey)}
              </h3>
              <p className="text-[13px] sm:text-sm leading-[1.7] text-stone-400 dark:text-stone-500">
                {t(`landing.${f.descKey}`, f.descKey)}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
