import { useTranslation } from "react-i18next";
import { Plus, Pencil } from "lucide-react";
import { EditorSidebar } from "../../common/EditorSidebar";
import { SkillForm } from "../../skill/SkillForm";
import type { SkillResponse, SkillCreate } from "../../../types";

interface SkillFormSidebarProps {
  showModal: boolean;
  isCreating: boolean;
  editingSkill: SkillResponse | null;
  isLoading: boolean;
  onSave: (data: SkillCreate) => Promise<boolean>;
  onCancel: () => void;
  createTitle?: string;
  subtitle?: string;
}

export function SkillFormSidebar({
  showModal,
  isCreating,
  editingSkill,
  isLoading,
  onSave,
  onCancel,
  createTitle,
  subtitle,
}: SkillFormSidebarProps) {
  const { t } = useTranslation();

  const title = isCreating
    ? createTitle ?? t("skills.createNew")
    : t("skills.editSkill", { name: editingSkill?.name });

  return (
    <EditorSidebar
      open={showModal}
      onClose={onCancel}
      title={title}
      subtitle={subtitle}
      icon={isCreating ? <Plus size={16} /> : <Pencil size={16} />}
    >
      <SkillForm
        skill={editingSkill}
        onSave={onSave}
        onCancel={onCancel}
        isLoading={isLoading}
      />
    </EditorSidebar>
  );
}
