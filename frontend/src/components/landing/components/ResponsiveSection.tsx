import { useTranslation } from "react-i18next";
import { RESPONSIVE_SHOTS } from "../data";
import { SectionHeading } from "./SectionHeading";
import { ZoomIcon } from "./Icons";

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
              <div className="relative">
                <img
                  src={s.src}
                  alt={t(`landing.${s.altKey}`)}
                  className="w-auto max-h-44 sm:max-h-72 lg:max-h-80 rounded-xl object-contain transition-transform duration-700 ease-out group-hover:scale-[1.02]"
                  loading="lazy"
                />
                <div className="absolute inset-0 bg-black/0 group-hover:bg-black/5 dark:group-hover:bg-black/20 transition-colors duration-400 flex items-center justify-center rounded-xl">
                  <div className="opacity-0 group-hover:opacity-100 transition-all duration-400 scale-75 group-hover:scale-100 w-10 h-10 rounded-full bg-white/95 dark:bg-stone-800/95 shadow-xl shadow-black/10 dark:shadow-black/30 flex items-center justify-center text-stone-400 dark:text-stone-500">
                    <ZoomIcon />
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
