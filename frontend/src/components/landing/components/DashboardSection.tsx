import { useTranslation } from "react-i18next";
import { MGMT_SHOTS } from "../data";
import { SectionHeading } from "./SectionHeading";
import { ScreenshotCard } from "./ScreenshotCard";

interface DashboardSectionProps {
  onOpenViewer: (src: string, alt: string) => void;
}

export function DashboardSection({ onOpenViewer }: DashboardSectionProps) {
  const { t } = useTranslation();

  return (
    <section
      id="dashboard"
      className="py-20 sm:py-28 lg:py-36 scroll-mt-14 bg-stone-50/70 dark:bg-stone-900/20"
    >
      <div className="max-w-5xl lg:max-w-6xl xl:max-w-7xl mx-auto px-5 sm:px-6">
        <SectionHeading
          label={t("landing.sectionLabelDashboard")}
          title={t("landing.managementPanels")}
          description={t("landing.managementPanelsDesc")}
        />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5">
          {MGMT_SHOTS.map((s) => (
            <ScreenshotCard
              key={s.src}
              src={s.src}
              alt={t(`landing.${s.altKey}`)}
              onClick={() => onOpenViewer(s.src, t(`landing.${s.altKey}`))}
            />
          ))}
        </div>
      </div>
    </section>
  );
}
