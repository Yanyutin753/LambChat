import { useTranslation } from "react-i18next";
import type { ScreenshotItem } from "../data";
import { SectionHeading } from "./SectionHeading";
interface ResponsiveSectionProps {
  shots: ScreenshotItem[];
  onOpenViewer: (src: string, alt: string) => void;
}

export function ResponsiveSection({
  shots,
  onOpenViewer,
}: ResponsiveSectionProps) {
  const { t } = useTranslation();

  return (
    <section
      id="responsive"
      className="blog-mesh-responsive py-20 sm:py-28 lg:py-36 scroll-mt-14"
    >
      <div className="max-w-5xl lg:max-w-6xl xl:max-w-7xl mx-auto px-5 sm:px-6">
        <SectionHeading
          label={t("landing.sectionLabelResponsive")}
          title={t("landing.responsiveDesign")}
          description={t("landing.responsiveDesignDesc")}
        />
        <div className="grid grid-cols-1 sm:grid-cols-[minmax(0,0.65fr)_minmax(0,1fr)] items-stretch gap-5 sm:gap-6 max-w-4xl mx-auto">
          {shots.map((s) => (
            <button
              type="button"
              aria-label={t(`landing.${s.altKey}`)}
              key={s.altKey}
              data-reveal-scale
              className="public-preview blog-screenshot-card group relative overflow-hidden cursor-pointer p-4 sm:p-6"
              onClick={() => onOpenViewer(s.src, t(`landing.${s.altKey}`))}
            >
              <img
                src={s.src}
                alt={t(`landing.${s.altKey}`)}
                loading="lazy"
                referrerPolicy="no-referrer"
                className="mx-auto w-auto max-w-full h-80 sm:h-[28rem] lg:h-[32rem] object-contain rounded-lg"
              />
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
