import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import { SkillForm } from "../../skill/SkillForm";
import type { SkillResponse, SkillCreate } from "../../../types";
import { useSwipeToClose } from "../../../hooks/useSwipeToClose";

interface SkillFormModalProps {
  showModal: boolean;
  isCreating: boolean;
  isFormFullscreen: boolean;
  editingSkill: SkillResponse | null;
  isLoading: boolean;
  onSave: (data: SkillCreate) => Promise<boolean>;
  onCancel: () => void;
  onFullscreenChange: (fullscreen: boolean) => void;
  /** Override the title shown in create mode (default: t("skills.createNew")) */
  createTitle?: string;
  /** Override the subtitle shown below the title */
  subtitle?: string;
}

export function SkillFormModal({
  showModal,
  isCreating,
  isFormFullscreen,
  editingSkill,
  isLoading,
  onSave,
  onCancel,
  onFullscreenChange,
  createTitle,
  subtitle,
}: SkillFormModalProps) {
  const { t } = useTranslation();
  const swipeRef = useSwipeToClose({
    onClose: onCancel,
    enabled: showModal && !isFormFullscreen,
  });

  if (!showModal) return null;

  return (
    <>
      {!isFormFullscreen && (
        <div className="fixed inset-0" onClick={onCancel} />
      )}
      <div className="modal-bottom-sheet sm:modal-centered-wrapper">
        <div
          ref={swipeRef as React.RefObject<HTMLDivElement>}
          className="modal-bottom-sheet-content sm:modal-centered-content sm:max-w-[72rem]"
        >
          {!isFormFullscreen && (
            <>
              <div className="bottom-sheet-handle sm:hidden" />
              <div className="skill-modal-header">
                <div>
                  <h3 className="skill-modal-header__title">
                    {isCreating
                      ? createTitle ?? t("skills.createNew")
                      : t("skills.editSkill", { name: editingSkill?.name })}
                  </h3>
                  <p className="skill-modal-header__subtitle">
                    {subtitle ?? t("skills.subtitle")}
                  </p>
                </div>
                <button onClick={onCancel} className="btn-icon">
                  <X size={20} />
                </button>
              </div>
            </>
          )}
          <div className="skill-modal-body flex flex-1 overflow-y-auto flex-col bg-[var(--theme-bg)]/30 px-3 py-3 sm:px-5 sm:py-4">
            <SkillForm
              skill={editingSkill}
              onSave={onSave}
              onCancel={onCancel}
              isLoading={isLoading}
              onFullscreenChange={onFullscreenChange}
            />
          </div>
        </div>
      </div>
    </>
  );
}
