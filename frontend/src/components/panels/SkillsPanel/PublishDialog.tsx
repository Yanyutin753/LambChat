import { useTranslation } from "react-i18next";
import { PackageX, Sparkles, Tag } from "lucide-react";
import { useSwipeToClose } from "../../../hooks/useSwipeToClose";

interface PublishConfirm {
  isOpen: boolean;
  localSkillName: string;
  marketplaceSkillName: string;
  description: string;
  tagsInput: string;
  isPublished: boolean;
  error?: string;
}

interface PublishDialogProps {
  publishConfirm: PublishConfirm | null;
  setPublishConfirm: (confirm: PublishConfirm | null) => void;
  onConfirm: () => void;
}

export function PublishDialog({
  publishConfirm,
  setPublishConfirm,
  onConfirm,
}: PublishDialogProps) {
  const { t } = useTranslation();
  const swipeRef = useSwipeToClose({
    onClose: () => setPublishConfirm(null),
    enabled: !!publishConfirm,
  });

  if (!publishConfirm) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 backdrop-blur-sm p-0 sm:items-center sm:p-4 animate-fade-in">
      <div
        ref={swipeRef as React.RefObject<HTMLDivElement>}
        className="skill-theme-shell w-full max-w-lg rounded-t-[1.75rem] border border-[var(--skill-border)] bg-[var(--skill-surface)] shadow-[0_28px_80px_-36px_rgba(15,23,42,0.55)] sm:rounded-[1.75rem] sm:animate-scale-in max-sm:animate-slide-up-sheet"
      >
        <div className="skill-modal-header">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-[var(--skill-border)] bg-[var(--skill-accent-soft)] text-[var(--skill-accent)]">
              <Sparkles className="h-5 w-5" />
            </div>
            <div>
              <h3 className="skill-modal-header__title">
                {publishConfirm.isPublished
                  ? t("skills.republishTitle", {
                      name: publishConfirm.localSkillName,
                    })
                  : t("skills.publishTitle", {
                      name: publishConfirm.localSkillName,
                    })}
              </h3>
              <p className="skill-modal-header__subtitle">
                {publishConfirm.isPublished
                  ? t("skills.republishMessage")
                  : t("skills.publishMessage")}
              </p>
            </div>
          </div>
        </div>
        <div className="space-y-5 p-5 sm:p-6">
          <div className="skill-modal-section">
            <div className="flex items-center gap-2">
              <PackageX className="h-3.5 w-3.5 text-[var(--theme-text-secondary)]" />
              <p className="text-xs font-medium uppercase tracking-wide text-[var(--theme-text-secondary)]">
                {t("skills.publishLocalSkill")}
              </p>
            </div>
            <p className="mt-1.5 font-mono text-sm text-[var(--theme-text)] break-all">
              {publishConfirm.localSkillName}
            </p>
          </div>

          <div className="space-y-1.5">
            <label className="block text-sm font-medium text-[var(--theme-text)]">
              {t("skills.publishMarketplaceName")}
            </label>
            <input
              type="text"
              value={publishConfirm.marketplaceSkillName}
              onChange={(e) =>
                setPublishConfirm({
                  ...publishConfirm,
                  marketplaceSkillName: e.target.value,
                  error: undefined,
                })
              }
              className="w-full rounded-xl border border-[var(--skill-border)] bg-[var(--theme-bg)] px-3.5 py-2.5 text-sm text-[var(--theme-text)] placeholder:text-[var(--theme-text-secondary)]/60 focus:border-[var(--skill-border-strong)] focus:outline-none focus:ring-2 focus:ring-[var(--skill-accent)]/14 transition-[border-color,box-shadow] duration-180"
            />
          </div>
          <div className="space-y-1.5">
            <label className="block text-sm font-medium text-[var(--theme-text)]">
              {t("skills.form.description")}
            </label>
            <textarea
              value={publishConfirm.description}
              onChange={(e) =>
                setPublishConfirm({
                  ...publishConfirm,
                  description: e.target.value,
                  error: undefined,
                })
              }
              rows={4}
              className="w-full rounded-xl border border-[var(--skill-border)] bg-[var(--theme-bg)] px-3.5 py-2.5 text-sm text-[var(--theme-text)] placeholder:text-[var(--theme-text-secondary)]/60 focus:border-[var(--skill-border-strong)] focus:outline-none focus:ring-2 focus:ring-[var(--skill-accent)]/14 transition-[border-color,box-shadow] duration-180 resize-none"
              placeholder={t("skills.form.descriptionPlaceholder")}
            />
          </div>
          <div className="space-y-1.5">
            <label className="flex items-center gap-1.5 text-sm font-medium text-[var(--theme-text)]">
              <Tag className="h-3.5 w-3.5 text-[var(--theme-text-secondary)]" />
              {t("adminMarketplace.tags")}
            </label>
            <p className="text-xs leading-5 text-[var(--theme-text-secondary)]/80">
              {t("adminMarketplace.tagsHint")}
            </p>
            <input
              type="text"
              value={publishConfirm.tagsInput}
              onChange={(e) =>
                setPublishConfirm({
                  ...publishConfirm,
                  tagsInput: e.target.value,
                  error: undefined,
                })
              }
              className="w-full rounded-xl border border-[var(--skill-border)] bg-[var(--theme-bg)] px-3.5 py-2.5 text-sm text-[var(--theme-text)] placeholder:text-[var(--theme-text-secondary)]/60 focus:border-[var(--skill-border-strong)] focus:outline-none focus:ring-2 focus:ring-[var(--skill-accent)]/14 transition-[border-color,box-shadow] duration-180"
              placeholder={t("adminMarketplace.tagsPlaceholder")}
            />
            <div className="mt-3 flex flex-wrap gap-2">
              {Array.from(
                new Set(
                  publishConfirm.tagsInput
                    .split(",")
                    .map((tag) => tag.trim())
                    .filter(Boolean),
                ),
              ).map((tag) => (
                <span
                  key={tag}
                  className="skill-tag-chip skill-tag-chip--active"
                >
                  {tag}
                </span>
              ))}
              {publishConfirm.tagsInput.trim().length === 0 && (
                <span className="text-xs text-[var(--theme-text-secondary)]/80">
                  {t("adminMarketplace.tagsPlaceholder")}
                </span>
              )}
            </div>
          </div>
          {publishConfirm.error && (
            <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-600 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-400">
              {publishConfirm.error}
            </div>
          )}
        </div>
        <div className="flex flex-col-reverse gap-2 border-t border-[color-mix(in_srgb,var(--theme-border)_40%,transparent)] px-5 py-4 sm:flex-row sm:justify-end sm:px-6">
          <button
            onClick={() => setPublishConfirm(null)}
            className="btn-secondary"
          >
            {t("common.cancel")}
          </button>
          <button onClick={onConfirm} className="btn-primary">
            {publishConfirm.isPublished
              ? t("skills.republish")
              : t("skills.publish")}
          </button>
        </div>
      </div>
    </div>
  );
}
