import { useTranslation } from "react-i18next";
import { STATS } from "../data";
import { SectionHeading } from "./SectionHeading";
import { AnimatedNumber } from "./AnimatedNumber";

interface ArchitectureSectionProps {
  onOpenViewer: (src: string, alt: string) => void;
}

export function ArchitectureSection({
  onOpenViewer,
}: ArchitectureSectionProps) {
  const { t } = useTranslation();

  return (
    <section
      id="architecture"
      className="py-20 sm:py-28 lg:py-36 scroll-mt-14 bg-stone-50/40 dark:bg-stone-900/10"
    >
      <div className="max-w-5xl lg:max-w-6xl mx-auto px-5 sm:px-6">
        <SectionHeading
          label={t("landing.sectionLabelArchitecture")}
          title={t("landing.architecture")}
          description={t("landing.architectureDesc")}
        />
        <div
          data-reveal-scale
          className="blog-arch-card group relative rounded-2xl overflow-hidden cursor-pointer bg-white/80 dark:bg-stone-900/30 transition-all duration-500 hover:-translate-y-1 hover:shadow-2xl"
          onClick={() =>
            onOpenViewer(
              "/images/best-practice/architecture.png",
              t("landing.architecture"),
            )
          }
        >
          <img
            src="/images/best-practice/architecture.png"
            alt={t("landing.architecture")}
            className="w-full transition-all duration-700 group-hover:brightness-[0.97]"
            loading="lazy"
          />
        </div>

        {/* Stats */}
        <div className="mt-14 sm:mt-18 grid grid-cols-2 sm:grid-cols-5 gap-3 sm:gap-4">
          {STATS.map((s, i) => (
            <div
              key={s.key}
              data-reveal
              data-reveal-delay={String(i + 1)}
              className={`blog-stat-card group relative rounded-2xl border border-stone-100/60 dark:border-stone-800/30 bg-white/80 dark:bg-stone-900/30 p-6 sm:p-7 text-center transition-all duration-500 hover:-translate-y-1.5 ${
                STATS.length % 2 !== 0 && i === STATS.length - 1
                  ? "col-span-2 sm:col-span-1"
                  : ""
              }`}
            >
              <div className="text-3xl sm:text-4xl font-extrabold font-serif tracking-tight text-transparent bg-clip-text bg-gradient-to-b from-stone-900 via-stone-800 to-stone-500 dark:from-stone-50 dark:via-stone-200 dark:to-stone-400 leading-none mb-2.5">
                <AnimatedNumber value={s.num} />
              </div>
              <div className="text-[11px] sm:text-xs font-medium text-stone-400 dark:text-stone-500 leading-snug">
                {t(`landing.${s.key}`, s.key)}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
