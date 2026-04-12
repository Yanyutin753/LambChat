import { useTranslation } from "react-i18next";
import { X, Archive, Upload, Sparkles } from "lucide-react";
import { LoadingSpinner } from "../../common/LoadingSpinner";
import { Checkbox } from "../../common/Checkbox";
import { useSwipeToClose } from "../../../hooks/useSwipeToClose";

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
  githubExporting: boolean;
  onGithubPreview: () => void;
  onGithubSkillToggle: (name: string) => void;
  onGithubInstall: () => void;
  onGithubExport: () => void;
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
  githubExporting,
  onGithubPreview,
  onGithubSkillToggle,
  onGithubInstall,
  onGithubExport,
  setSelectedGithubSkills,
}: GithubImportModalProps) {
  const { t } = useTranslation();
  const swipeRef = useSwipeToClose({
    onClose: () => setShowGithubModal(false),
    enabled: showGithubModal,
  });

  if (!showGithubModal) return null;

  return (
    <>
      <div
        className="fixed inset-0 z-[299] bg-black/50 sm:bg-transparent"
        onClick={githubInstalling ? undefined : () => setShowGithubModal(false)}
      />
      <div
        className="modal-bottom-sheet sm:modal-centered-wrapper"
        onClick={githubInstalling ? undefined : () => setShowGithubModal(false)}
      >
        <div
          ref={swipeRef as React.RefObject<HTMLDivElement>}
          className="modal-bottom-sheet-content sm:modal-centered-content sm:max-w-[72rem]"
        >
          <div className="bottom-sheet-handle sm:hidden" />
          <div className="skill-modal-header">
            <div>
              <h3 className="skill-modal-header__title">
                {t("skills.importFromGitHub")}
              </h3>
              <p className="skill-modal-header__subtitle">
                {t("skills.subtitle")}
              </p>
            </div>
            <button
              onClick={() => setShowGithubModal(false)}
              disabled={githubInstalling}
              className="btn-icon disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <X size={20} />
            </button>
          </div>
          <div className="skill-modal-body flex-1 overflow-y-auto px-3 py-4 sm:px-6 sm:py-5">
            <div className="skill-modal-section space-y-4">
              <div className="skill-callout flex items-start gap-3 rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg)]/85 px-4 py-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[var(--theme-primary-light)] text-[var(--theme-primary)]">
                  <Sparkles size={18} />
                </div>
                <div>
                  <p className="text-sm font-medium text-[var(--theme-text)]">
                    {t("skills.importFromGitHub")}
                  </p>
                  <p className="mt-1 text-xs leading-5 text-[var(--theme-text-secondary)]">
                    {t("skills.importFromGitHubTitle")}
                  </p>
                </div>
              </div>
              {/* URL Input */}
              <div className="space-y-2">
                <label className="block text-sm font-medium text-stone-700 dark:text-stone-300">
                  {t("skills.githubRepoUrl")}
                </label>
                <div className="skill-github-import flex flex-col gap-2 sm:flex-row">
                  <div className="skill-github-import__field skill-github-import__field--repo">
                    <input
                      type="text"
                      value={githubUrl}
                      onChange={(e) => setGithubUrl(e.target.value)}
                      placeholder="https://github.com/owner/repo"
                      className="input-field skill-github-import__input"
                    />
                  </div>
                  <div className="skill-github-import__field skill-github-import__field--branch">
                    <input
                      type="text"
                      value={githubBranch}
                      onChange={(e) => setGithubBranch(e.target.value)}
                      placeholder="main"
                      className="input-field skill-github-import__input"
                    />
                  </div>
                  <button
                    onClick={onGithubPreview}
                    disabled={githubLoading || !githubUrl.trim()}
                    className="btn-secondary skill-github-import__button"
                  >
                    {githubLoading ? (
                      <LoadingSpinner size="sm" />
                    ) : (
                      t("skills.preview")
                    )}
                  </button>
                </div>
              </div>

              {githubSkills.length > 0 && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <label className="text-sm font-medium text-[var(--theme-text)]">
                        {t("skills.selectSkillsToInstall")}
                      </label>
                      <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-[var(--theme-primary)]/10 px-1.5 text-[11px] font-semibold text-[var(--theme-primary)]">
                        {selectedGithubSkills.length}/{githubSkills.length}
                      </span>
                    </div>
                    <button
                      onClick={() => {
                        const allNames = githubSkills.map((s) => s.name);
                        setSelectedGithubSkills(
                          selectedGithubSkills.length === allNames.length
                            ? []
                            : allNames,
                        );
                      }}
                      className="rounded-md px-2 py-1 text-xs font-medium text-[var(--theme-primary)] transition-colors hover:bg-[var(--theme-primary)]/8"
                    >
                      {selectedGithubSkills.length === githubSkills.length
                        ? t("common.deselectAll")
                        : t("common.selectAll")}
                    </button>
                  </div>
                  <div className="space-y-1.5 max-h-60 overflow-y-auto rounded-xl p-1">
                    {githubSkills.map((skill) => {
                      const selected = selectedGithubSkills.includes(
                        skill.name,
                      );
                      return (
                        <div
                          key={skill.name}
                          onClick={() => onGithubSkillToggle(skill.name)}
                          className={`group flex cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 transition-all duration-150 ${
                            selected
                              ? "bg-[var(--theme-primary)]/8"
                              : "hover:bg-[var(--theme-primary)]/4"
                          }`}
                        >
                          <Checkbox
                            size="sm"
                            checked={selected}
                            onChange={() => onGithubSkillToggle(skill.name)}
                          />
                          <div className="flex-1 min-w-0">
                            <p
                              className={`text-sm font-medium truncate transition-colors ${
                                selected
                                  ? "text-[var(--theme-primary)]"
                                  : "text-[var(--theme-text)]"
                              }`}
                            >
                              {skill.name}
                            </p>
                            {skill.description && (
                              <p className="mt-0.5 text-xs text-[var(--theme-text-secondary)] truncate">
                                {skill.description}
                              </p>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              <div className="flex justify-end gap-2 border-t border-[color-mix(in_srgb,var(--theme-border)_40%,transparent)] pt-4">
                <button
                  onClick={() => setShowGithubModal(false)}
                  className="btn-secondary"
                >
                  {t("common.cancel")}
                </button>
                <button
                  onClick={onGithubExport}
                  disabled={
                    githubExporting || selectedGithubSkills.length === 0
                  }
                  className="btn-secondary disabled:opacity-50"
                >
                  {githubExporting ? (
                    <>
                      <LoadingSpinner size="sm" />
                      {t("skills.exportZip")}
                    </>
                  ) : (
                    <>
                      <Archive size={18} />
                      {t("skills.exportZip")}
                    </>
                  )}
                </button>
                <button
                  onClick={onGithubInstall}
                  disabled={
                    githubInstalling || selectedGithubSkills.length === 0
                  }
                  className="btn-primary disabled:opacity-50"
                >
                  {githubInstalling ? (
                    <>
                      <LoadingSpinner size="sm" color="text-white" />
                      {t("skills.installing")}
                    </>
                  ) : (
                    <>
                      <Upload size={18} />
                      {t("skills.installSelected", {
                        count: selectedGithubSkills.length,
                      })}
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
