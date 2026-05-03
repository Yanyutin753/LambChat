import { useTranslation, Trans } from "react-i18next";
import {
  Scale,
  ShieldAlert,
  Bot,
  Ban,
  BookOpen,
  AlertTriangle,
  Eye,
} from "lucide-react";

const TERMS_LINK =
  "https://www.gov.cn/zhengce/zhengceku/202307/content_6891752.htm";

const regulationLink = (
  <a
    href={TERMS_LINK}
    target="_blank"
    rel="noopener noreferrer"
    className="relative inline-flex items-center gap-0.5 text-amber-600 dark:text-amber-400 font-medium hover:text-amber-700 dark:hover:text-amber-300 underline decoration-amber-400/40 dark:decoration-amber-500/30 underline-offset-2 transition-colors after:content-['↗'] after:text-[9px] after:ml-0.5 after:opacity-60"
  />
);

const items = [
  {
    icon: BookOpen,
    color: "text-amber-500 dark:text-amber-400",
    ring: "ring-amber-500/10",
    border: "border-amber-200/50 dark:border-amber-500/15",
    bg: "bg-amber-50/70 dark:bg-amber-500/5",
    key: "termsItem1",
    useTrans: true,
  },
  {
    icon: Bot,
    color: "text-stone-400 dark:text-stone-500",
    ring: "ring-stone-400/10",
    border: "border-stone-200/50 dark:border-stone-600/25",
    bg: "bg-stone-50/70 dark:bg-stone-700/20",
    key: "termsItem2",
    useTrans: false,
  },
  {
    icon: Ban,
    color: "text-red-500 dark:text-red-400",
    ring: "ring-red-500/10",
    border: "border-red-200/50 dark:border-red-500/15",
    bg: "bg-red-50/70 dark:bg-red-500/5",
    key: "termsItem3",
    useTrans: true,
  },
  {
    icon: ShieldAlert,
    color: "text-orange-500 dark:text-orange-400",
    ring: "ring-orange-500/10",
    border: "border-orange-200/50 dark:border-orange-500/15",
    bg: "bg-orange-50/70 dark:bg-orange-500/5",
    key: "termsItem4",
    useTrans: false,
    bold: true,
  },
  {
    icon: AlertTriangle,
    color: "text-orange-500 dark:text-orange-400",
    ring: "ring-orange-500/10",
    border: "border-orange-200/50 dark:border-orange-500/15",
    bg: "bg-orange-50/70 dark:bg-orange-500/5",
    key: "termsItem5",
    useTrans: false,
    bold: true,
  },
  {
    icon: Eye,
    color: "text-sky-500 dark:text-sky-400",
    ring: "ring-sky-500/10",
    border: "border-sky-200/50 dark:border-sky-500/15",
    bg: "bg-sky-50/70 dark:bg-sky-500/5",
    key: "termsItem6",
    useTrans: false,
    bold: true,
  },
];

export function ProfileTermsTab() {
  const { t } = useTranslation();

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-gradient-to-br from-amber-400 to-amber-500 shadow-sm shadow-amber-500/20">
          <Scale size={16} className="text-white" />
        </div>
        <div>
          <h3 className="text-sm font-bold text-stone-800 dark:text-stone-100 tracking-tight">
            {t("profile.termsTitle")}
          </h3>
          <p className="text-[11px] text-stone-400 dark:text-stone-500 mt-px">
            Terms of Service
          </p>
        </div>
      </div>

      {/* Divider */}
      <div className="h-px bg-gradient-to-r from-stone-200 via-stone-200/60 to-transparent dark:from-stone-700 dark:via-stone-700/40 dark:to-transparent" />

      {/* Items */}
      <div className="space-y-2">
        {items.map((item, i) => {
          const Icon = item.icon;
          const content = item.useTrans ? (
            <Trans
              i18nKey={`profile.${item.key}`}
              components={{ a: regulationLink, strong: <strong /> }}
            />
          ) : item.bold ? (
            <strong>{t(`profile.${item.key}`)}</strong>
          ) : (
            t(`profile.${item.key}`)
          );

          return (
            <div
              key={i}
              className={`group flex items-center gap-3 p-3 rounded-xl border ${item.border} ${item.bg} ring-1 ring-inset ${item.ring} transition-all duration-200 hover:shadow-sm hover:brightness-[0.98] dark:hover:brightness-110`}
            >
              <div
                className={`shrink-0 flex items-center justify-center w-7 h-7 rounded-lg bg-white dark:bg-stone-800/80 border border-stone-200/80 dark:border-stone-600/40 shadow-[0_1px_2px_rgba(0,0,0,0.04)]`}
              >
                <Icon size={14} className={item.color} />
              </div>
              <p
                className="m-0 text-xs leading-relaxed text-stone-600 dark:text-stone-300"
                style={{ textAlign: "justify" }}
              >
                {content}
              </p>
            </div>
          );
        })}
      </div>

      {/* Footer note */}
      <p className="text-[10px] text-center text-stone-400 dark:text-stone-500 pt-1">
        {t("auth.termsHint")}
      </p>
    </div>
  );
}
