import { useTranslation } from "react-i18next";
import { RESPONSIVE_SHOTS } from "../data";
import { SectionHeading } from "./SectionHeading";
interface ResponsiveSectionProps {
  onOpenViewer: (src: string, alt: string) => void;
}

export function ResponsiveSection({ onOpenViewer }: ResponsiveSectionProps) {
  const { t } = useTranslation();

  return (
    <section id="responsive" className="py-20 sm:py-28 lg:py-36 scroll-mt-14">
      <div className="max-w-5xl lg:max-w-6xl xl:max-w-7xl mx-auto px-5 sm:px-6">
        <SectionHeading
          label={t("landing.sectionLabelResponsive")}
          title={t("landing.responsiveDesign")}
          description={t("landing.responsiveDesignDesc")}
        />
        <div className="flex flex-col sm:flex-row items-center justify-center gap-5 sm:gap-8">
          {RESPONSIVE_SHOTS.map((s) => (
            <div
              key={s.src}
              data-reveal-scale
              className="blog-screenshot-card group relative rounded-2xl overflow-hidden cursor-pointer bg-white dark:bg-stone-900/50 p-3 sm:p-4 transition-all duration-500 hover:-translate-y-1.5"
              onClick={() => onOpenViewer(s.src, t(`landing.${s.altKey}`))}
            >
              <img
                src={s.src}
                alt={t(`landing.${s.altKey}`)}
                className="w-auto max-h-44 sm:max-h-72 lg:max-h-80 rounded-xl object-contain"
                loading="lazy"
              />
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
