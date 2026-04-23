import { useTranslation } from "react-i18next";
import { MAIN_SHOTS } from "../data";
import { SectionHeading } from "./SectionHeading";
import { ScreenshotCard } from "./ScreenshotCard";

interface InterfaceSectionProps {
  onOpenViewer: (src: string, alt: string) => void;
}

export function InterfaceSection({ onOpenViewer }: InterfaceSectionProps) {
  const { t } = useTranslation();

  return (
    <section
      id="interface"
      className="blog-mesh-interface py-20 sm:py-28 lg:py-36 scroll-mt-14 bg-stone-50/50 dark:bg-stone-900/15"
    >
      <div className="max-w-5xl lg:max-w-6xl xl:max-w-7xl mx-auto px-5 sm:px-6">
        <SectionHeading
          label={t("landing.sectionLabelInterface")}
          title={t("landing.mainInterface")}
          description={t("landing.mainInterfaceDesc")}
        />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 sm:gap-6">
          {MAIN_SHOTS.map((s) => (
            <ScreenshotCard
              key={s.src}
              src={s.src}
              alt={t(`landing.${s.altKey}`)}
              onClick={() => onOpenViewer(s.src, t(`landing.${s.altKey}`))}
              label={t("landing.preview")}
            />
          ))}
        </div>
      </div>
    </section>
  );
}
