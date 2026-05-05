import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { ShieldCheck, Mail, ExternalLink, ArrowRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useSettings } from "../../hooks/useSettings";

interface ContactAdminDialogProps {
  isOpen: boolean;
  onClose: () => void;
  reason?: "noPermission" | "emailActivation";
}

export function ContactAdminDialog({
  isOpen,
  onClose,
  reason = "noPermission",
}: ContactAdminDialogProps) {
  const { t } = useTranslation();
  const { getSettingValue } = useSettings();
  const closeRef = useRef<HTMLButtonElement>(null);

  const adminEmail = getSettingValue("ADMIN_CONTACT_EMAIL") as string | null;
  const adminUrl = getSettingValue("ADMIN_CONTACT_URL") as string | null;

  useEffect(() => {
    if (isOpen) {
      closeRef.current?.focus();
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (isOpen && e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const title =
    reason === "emailActivation"
      ? t("contactAdmin.emailActivationTitle", "邮箱验证问题")
      : t("contactAdmin.noPermissionTitle", "权限不足");

  const description =
    reason === "emailActivation"
      ? t(
          "contactAdmin.emailActivationDesc",
          "您的邮箱尚未验证或验证链接已过期，请联系管理员获取帮助。",
        )
      : t(
          "contactAdmin.noPermissionDesc",
          "您当前没有发送消息的权限。如需开通，请联系管理员。",
        );

  const hasContact = adminEmail || adminUrl;

  return createPortal(
    <div
      data-yields-sidebar
      className="fixed inset-0 z-[300] flex items-center justify-center p-4"
    >
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative z-10 w-full max-w-[420px] rounded-2xl border border-stone-200/60 bg-white shadow-2xl shadow-stone-900/8 dark:border-stone-700/50 dark:bg-stone-900 dark:shadow-stone-950/40 animate-in fade-in zoom-in-95 duration-200">
        {/* Header illustration */}
        <div className="relative overflow-hidden rounded-t-2xl bg-gradient-to-b from-amber-50/80 to-white px-8 pb-7 pt-9 dark:from-amber-950/20 dark:to-stone-900">
          <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-amber-300/40 to-transparent dark:via-amber-700/30" />
          <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-white shadow-sm shadow-stone-900/5 ring-1 ring-stone-900/5 dark:bg-stone-800 dark:ring-stone-700/60 dark:shadow-none">
            <ShieldCheck className="h-7 w-7 text-amber-500 dark:text-amber-400" />
          </div>
          <div className="text-center">
            <h3 className="text-base font-semibold tracking-tight text-stone-900 dark:text-stone-50">
              {title}
            </h3>
            <p className="mt-2 text-sm leading-relaxed text-stone-500 dark:text-stone-400">
              {description}
            </p>
          </div>
        </div>

        {/* Contact methods */}
        <div className="px-5 py-5">
          {hasContact ? (
            <div className="space-y-2.5">
              {adminEmail && (
                <a
                  href={`mailto:${adminEmail}`}
                  className="group flex items-center gap-3 rounded-xl border border-stone-100 bg-stone-50/50 px-4 py-3 text-sm text-stone-600 transition-all hover:border-stone-200 hover:bg-white hover:shadow-sm dark:border-stone-800 dark:bg-stone-800/40 dark:text-stone-300 dark:hover:border-stone-700 dark:hover:bg-stone-800/70"
                >
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white shadow-sm ring-1 ring-stone-900/5 dark:bg-stone-700 dark:ring-stone-600/50 dark:shadow-none">
                    <Mail size={15} className="text-stone-400" />
                  </div>
                  <span className="flex-1 truncate">{adminEmail}</span>
                  <ArrowRight
                    size={15}
                    className="text-stone-300 transition-transform group-hover:translate-x-0.5 dark:text-stone-600"
                  />
                </a>
              )}
              {adminUrl && (
                <a
                  href={adminUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="group flex items-center gap-3 rounded-xl border border-stone-100 bg-stone-50/50 px-4 py-3 text-sm text-stone-600 transition-all hover:border-stone-200 hover:bg-white hover:shadow-sm dark:border-stone-800 dark:bg-stone-800/40 dark:text-stone-300 dark:hover:border-stone-700 dark:hover:bg-stone-800/70"
                >
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white shadow-sm ring-1 ring-stone-900/5 dark:bg-stone-700 dark:ring-stone-600/50 dark:shadow-none">
                    <ExternalLink size={15} className="text-stone-400" />
                  </div>
                  <span className="flex-1">
                    {t("contactAdmin.supportLink", "联系管理员")}
                  </span>
                  <ArrowRight
                    size={15}
                    className="text-stone-300 transition-transform group-hover:translate-x-0.5 dark:text-stone-600"
                  />
                </a>
              )}
            </div>
          ) : (
            <div className="rounded-xl border border-stone-100 bg-stone-50/50 px-4 py-4 text-center dark:border-stone-800 dark:bg-stone-800/40">
              <p className="text-sm text-stone-400 dark:text-stone-500">
                {t(
                  "contactAdmin.noContactInfo",
                  "暂无管理员联系方式，请联系系统管理员。",
                )}
              </p>
            </div>
          )}
        </div>

        {/* Close */}
        <div className="px-5 pb-6 pt-1">
          <button
            ref={closeRef}
            onClick={onClose}
            className="w-full rounded-xl bg-stone-900 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:bg-stone-800 active:bg-stone-700 dark:bg-stone-100 dark:text-stone-900 dark:hover:bg-stone-200 dark:active:bg-stone-300"
          >
            {t("common.close", "关闭")}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
