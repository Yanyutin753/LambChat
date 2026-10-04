import { DialogCloseButton } from "../../common/DialogCloseButton";
import { ModalSurface } from "../../common/ModalSurface";
import { useTranslation } from "react-i18next";
import { Tag } from "lucide-react";

import { Button, FormField, Input, Textarea } from "../../common";
import { ResourceCardTags } from "../../common/ResourceCardTags";
import { ConfigPanelErrorCallout } from "../ConfigPanelErrorCallout";

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
  isPublishing?: boolean;
}

export function PublishDialog({
  publishConfirm,
  setPublishConfirm,
  onConfirm,
  isPublishing = false,
}: PublishDialogProps) {
  const { t } = useTranslation();

  if (!publishConfirm) return null;

  return (
    <ModalSurface
      open
      dismissible={!isPublishing}
      onClose={() => setPublishConfirm(null)}
      className="modal-size-lg"
    >
      <form
        aria-label={t(
          publishConfirm.isPublished
            ? "skills.republishTitle"
            : "skills.publishTitle",
          { name: publishConfirm.localSkillName },
        )}
        aria-busy={isPublishing || undefined}
        onSubmit={(event) => {
          event.preventDefault();
          if (!isPublishing) {
            event.currentTarget
              .closest<HTMLElement>("[data-modal-surface]")
              ?.focus();
            onConfirm();
          }
        }}
        className="skill-theme-shell w-full max-w-lg flex min-h-0 flex-col overflow-hidden rounded-2xl border border-[var(--skill-border)] bg-[var(--skill-surface)] safe-area-bottom"
      >
        <div className="skill-modal-header shrink-0 !px-5 sm:!px-6">
          <div className="flex items-center gap-3">
            <div className="min-w-0">
              <h3 className="skill-modal-header__title font-serif [overflow-wrap:anywhere]">
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
          <DialogCloseButton
            disabled={isPublishing}
            onClick={() => setPublishConfirm(null)}
          />
        </div>
        <div className="min-h-0 overflow-y-auto space-y-5 p-5 sm:p-6">
          <div>
            <div className="flex items-center gap-2">
              <p className="text-12 text-theme-text-secondary">
                {t("skills.publishLocalSkill")}
              </p>
            </div>
            <p className="mt-1.5 font-mono text-14 text-[var(--theme-text)] break-all">
              {publishConfirm.localSkillName}
            </p>
          </div>

          <FormField label={t("skills.publishMarketplaceName")}>
            <Input
              type="text"
              disabled={isPublishing}
              value={publishConfirm.marketplaceSkillName}
              onChange={(e) =>
                setPublishConfirm({
                  ...publishConfirm,
                  marketplaceSkillName: e.target.value,
                  error: undefined,
                })
              }
              className="!min-h-11 sm:!min-h-9"
            />
          </FormField>
          <FormField label={t("skills.form.description")}>
            <Textarea
              disabled={isPublishing}
              value={publishConfirm.description}
              onChange={(e) =>
                setPublishConfirm({
                  ...publishConfirm,
                  description: e.target.value,
                  error: undefined,
                })
              }
              rows={4}
              placeholder={t("skills.form.descriptionPlaceholder")}
            />
          </FormField>
          <FormField
            label={
              <span className="flex items-center gap-1.5">
                <Tag className="h-3.5 w-3.5 text-[var(--theme-text-secondary)]" />
                {t("adminMarketplace.tags")}
              </span>
            }
            hint={t("adminMarketplace.tagsHint")}
          >
            <Input
              type="text"
              disabled={isPublishing}
              value={publishConfirm.tagsInput}
              onChange={(e) =>
                setPublishConfirm({
                  ...publishConfirm,
                  tagsInput: e.target.value,
                  error: undefined,
                })
              }
              className="!min-h-11 sm:!min-h-9"
              placeholder={t("adminMarketplace.tagsPlaceholder")}
            />
            <div className="mt-3 min-w-0">
              <ResourceCardTags
                tags={Array.from(
                  new Set(
                    publishConfirm.tagsInput
                      .split(",")
                      .map((tag) => tag.trim())
                      .filter(Boolean),
                  ),
                )}
              />
              {publishConfirm.tagsInput.trim().length === 0 && (
                <span className="text-12 text-[var(--theme-text-secondary)]/80">
                  {t("adminMarketplace.tagsPlaceholder")}
                </span>
              )}
            </div>
          </FormField>
          {publishConfirm.error && (
            <ConfigPanelErrorCallout message={publishConfirm.error} />
          )}
        </div>
        <div className="shrink-0 flex flex-col-reverse gap-1 px-5 py-4 sm:flex-row sm:justify-end sm:px-6">
          <Button
            variant="secondary"
            disabled={isPublishing}
            className="!min-h-11 sm:!min-h-9"
            onClick={() => setPublishConfirm(null)}
          >
            {t("common.cancel")}
          </Button>
          <Button
            variant="primary"
            type="submit"
            loading={isPublishing}
            className="!min-h-11 sm:!min-h-9"
          >
            {publishConfirm.isPublished
              ? t("skills.republish")
              : t("skills.publish")}
          </Button>
        </div>
      </form>
    </ModalSurface>
  );
}
