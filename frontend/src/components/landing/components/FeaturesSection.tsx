import { useTranslation } from "react-i18next";
import { FEATURES } from "../data";
import { SectionHeading } from "./SectionHeading";

export function FeaturesSection() {
  const { t } = useTranslation();

  return (
    <section
      id="features"
      className="blog-mesh-features py-20 sm:py-28 lg:py-36 relative scroll-mt-14"
    >
      <div className="max-w-5xl lg:max-w-6xl xl:max-w-7xl mx-auto px-5 sm:px-6">
        <SectionHeading
          label={t("landing.sectionLabelFeatures")}
          title={t("landing.coreFeatures")}
          description={t("landing.coreFeaturesDesc")}
        />
        <div className="landing-capability-grid">
          {[
            [0, 8],
            [1, 10],
            [2, 9],
            [3, 4],
            [5, 6],
            [7, 11],
          ].map(([primary, related], i) => {
            const feature = FEATURES[primary];
            return (
              <article
                key={feature.titleKey}
                data-reveal
                className="landing-capability"
              >
                <span className="landing-capability-index" aria-hidden="true">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <div>
                  <h3 className="font-serif text-20 text-theme-text mb-3">
                    {t(`landing.${feature.titleKey}`)}
                  </h3>
                  <p className="text-14 leading-[1.8] text-theme-text-secondary">
                    {t(`landing.${feature.descKey}`)}
                  </p>
                  <p className="mt-4 text-12 text-theme-text-muted">
                    {t(`landing.${FEATURES[related].titleKey}`)}
                  </p>
                </div>
              </article>
            );
          })}
        </div>
      </div>
    </section>
  );
}
