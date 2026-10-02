import { useTranslation } from "react-i18next";
import { Github, Upload } from "lucide-react";
import { EditorSidebar } from "../../common/EditorSidebar";
import { Checkbox } from "../../common/Checkbox";
import { Button, FormField, Input } from "../../common";
import { ConfigPanelErrorCallout } from "../ConfigPanelErrorCallout";

interface GitHubSkill {
  name: string;
  path: string;
  description: string;
}
interface GithubImportModalProps {
  showGithubModal: boolean;
  setShowGithubModal: (show: boolean) => void;
  githubUrl: string;
  setGithubUrl: (url: string) => void;
  githubBranch: string;
  setGithubBranch: (branch: string) => void;
  githubSkills: GitHubSkill[];
  selectedGithubSkills: string[];
  githubLoading: boolean;
  githubInstalling: boolean;
  githubPreviewed: boolean;
  githubError: string | null;
  onGithubPreview: () => void;
  onGithubSkillToggle: (name: string) => void;
  onGithubInstall: () => void;
  setSelectedGithubSkills: (skills: string[]) => void;
}

export function GithubImportModal({
  showGithubModal,
  setShowGithubModal,
  githubUrl,
  setGithubUrl,
  githubBranch,
  setGithubBranch,
  githubSkills,
  selectedGithubSkills,
  githubLoading,
  githubInstalling,
  githubPreviewed,
  githubError,
  onGithubPreview,
  onGithubSkillToggle,
  onGithubInstall,
  setSelectedGithubSkills,
}: GithubImportModalProps) {
  const { t } = useTranslation();
  return (
    <EditorSidebar
      open={showGithubModal}
      onClose={() => setShowGithubModal(false)}
      title={t("skills.importFromGitHub")}
      icon={<Github size={16} />}
      width="wide"
      footer={
        <div className="flex flex-wrap justify-end gap-1">
          <Button
            variant="secondary"
            onClick={() => setShowGithubModal(false)}
            disabled={githubInstalling}
          >
            {t("common.cancel")}
          </Button>
          <Button
            variant="primary"
            onClick={onGithubInstall}
            loading={githubInstalling}
            leftIcon={<Upload size={16} />}
            disabled={githubLoading || selectedGithubSkills.length === 0}
          >
            {t("skills.installSelected", {
              count: selectedGithubSkills.length,
            })}
          </Button>
        </div>
      }
    >
      <div className="es-form">
        <FormField label={t("skills.githubRepoUrl")}>
          <Input
            value={githubUrl}
            onChange={(e) => setGithubUrl(e.target.value)}
            disabled={githubInstalling}
            autoComplete="off"
            spellCheck={false}
            placeholder="https://github.com/owner/repo"
          />
        </FormField>
        <FormField label={t("skills.githubBranch")}>
          <Input
            value={githubBranch}
            onChange={(e) => setGithubBranch(e.target.value)}
            disabled={githubInstalling}
            autoComplete="off"
            spellCheck={false}
            placeholder="main"
          />
        </FormField>
        <Button
          variant="secondary"
          onClick={onGithubPreview}
          loading={githubLoading}
          disabled={githubInstalling || !githubUrl.trim()}
        >
          {t("skills.preview")}
        </Button>
        {githubError && (
          <div className="space-y-2">
            <ConfigPanelErrorCallout message={githubError} />
            <Button
              onClick={(event) => {
                event.currentTarget
                  .closest<HTMLElement>("[data-right-panel-root]")
                  ?.focus();
                if (githubPreviewed) onGithubInstall();
                else onGithubPreview();
              }}
              disabled={
                githubLoading ||
                githubInstalling ||
                (githubPreviewed && selectedGithubSkills.length === 0)
              }
            >
              {t("common.retry")}
            </Button>
          </div>
        )}
        {githubPreviewed &&
          !githubLoading &&
          !githubError &&
          githubSkills.length === 0 && (
            <p role="status" className="text-14 text-theme-text-secondary">
              {t("backendErrors.noSkillsFoundInRepository")}
            </p>
          )}
        {githubSkills.length > 0 && (
          <div className="es-section space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-14 font-medium text-theme-text">
                {t("skills.selectSkillsToInstall")}{" "}
                <span className="text-12 text-theme-text-secondary tabular-nums">
                  {selectedGithubSkills.length}/{githubSkills.length}
                </span>
              </p>
              <Button
                variant="ghost"
                size="sm"
                disabled={githubInstalling || githubLoading}
                onClick={() =>
                  setSelectedGithubSkills(
                    selectedGithubSkills.length === githubSkills.length
                      ? []
                      : githubSkills.map((s) => s.name),
                  )
                }
              >
                {selectedGithubSkills.length === githubSkills.length
                  ? t("common.deselectAll")
                  : t("common.selectAll")}
              </Button>
            </div>
            <div className="space-y-1.5">
              {githubSkills.map((skill) => (
                <label
                  key={skill.name}
                  className={`flex cursor-pointer items-start gap-3 rounded-lg px-3 py-3 ${selectedGithubSkills.includes(skill.name) ? "bg-theme-primary-light" : "hover:bg-theme-bg-subtle"}`}
                >
                  <Checkbox
                    ariaLabel={skill.name}
                    size="sm"
                    checked={selectedGithubSkills.includes(skill.name)}
                    disabled={githubInstalling || githubLoading}
                    onChange={() => onGithubSkillToggle(skill.name)}
                    className="mt-0.5"
                  />
                  <div className="min-w-0 flex-1">
                    <p className="text-14 font-medium text-theme-text [overflow-wrap:anywhere]">
                      {skill.name}
                    </p>
                    {skill.description && (
                      <p className="mt-0.5 text-12 text-theme-text-secondary [overflow-wrap:anywhere]">
                        {skill.description}
                      </p>
                    )}
                  </div>
                </label>
              ))}
            </div>
          </div>
        )}
      </div>
    </EditorSidebar>
  );
}
