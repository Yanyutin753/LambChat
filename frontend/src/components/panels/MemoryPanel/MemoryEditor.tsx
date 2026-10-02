import { useState, useRef, useId, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Plus, Pencil, Save } from "lucide-react";
import toast from "react-hot-toast";
import { EditorSidebar } from "../../common/EditorSidebar";
import {
  Button,
  FormField,
  Input,
  PanelFooterActions,
  Textarea,
} from "../../common";
import { memoryApi, type MemoryItem } from "../../../services/api/memory";
import { Loading } from "../../common/LoadingSpinner";
import { ConfigPanelErrorCallout } from "../ConfigPanelErrorCallout";
import { useMemoryContent } from "./useMemoryContent";
import {
  TYPE_OPTIONS_LIST,
  TYPE_STYLES,
  TYPE_DOTS,
  SOURCE_OPTIONS_LIST,
  SOURCE_STYLES,
  SOURCE_DOTS,
} from "./constants";

export function MemoryEditor({
  memory,
  onClose,
  onSaved,
  relativeTime,
}: {
  memory?: MemoryItem | null;
  onClose: () => void;
  onSaved: () => void;
  relativeTime: (dateStr: string | null) => string;
}) {
  const { t } = useTranslation();
  const formId = useId();
  const isEdit = !!memory;

  const [title, setTitle] = useState(memory?.title ?? "");
  const [contentDraft, setContent] = useState<string | null>(null);
  const [summaryDraft, setSummary] = useState<string | null>(null);
  const [memoryType, setMemoryType] = useState(memory?.memory_type ?? "user");
  const [source, setSource] = useState(memory?.source ?? "manual");
  const [tagsInput, setTagsInput] = useState(memory?.tags?.join(", ") ?? "");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(false);
  const {
    full,
    loading: loadingContent,
    error: loadError,
    retry,
  } = useMemoryContent(memory);
  const content = contentDraft ?? full?.content ?? "";
  const summary = summaryDraft ?? full?.summary ?? memory?.summary ?? "";
  const contentRef = useRef<HTMLDivElement>(null);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const handleSave = async () => {
    if (saving || loadingContent || loadError) return;
    if (!content.trim() || content.trim().length < 5) {
      toast.error(t("memory.contentRequired"));
      return;
    }
    contentRef.current?.focus({ preventScroll: true });
    setSaveError(false);
    setSaving(true);
    try {
      const tags = tagsInput
        .split(/[,，]/)
        .map((t) => t.trim())
        .filter(Boolean);

      if (isEdit && memory) {
        await memoryApi.update(memory.memory_id, {
          title: title.trim() || undefined,
          content: content.trim(),
          summary: summary.trim() || undefined,
          memory_type: memoryType,
          tags,
          source,
        });
        toast.success(t("memory.updateSuccess"));
      } else {
        await memoryApi.create({
          title: title.trim() || undefined,
          content: content.trim(),
          summary: summary.trim() || undefined,
          memory_type: memoryType,
          tags,
        });
        toast.success(t("memory.createSuccess"));
      }
      onSaved();
      if (mounted.current) onClose();
    } catch {
      if (mounted.current) setSaveError(true);
    } finally {
      if (mounted.current) setSaving(false);
    }
  };

  return (
    <EditorSidebar
      open={true}
      onClose={onClose}
      title={isEdit ? t("memory.editTitle") : t("memory.createTitle")}
      icon={isEdit ? <Pencil size={16} /> : <Plus size={16} />}
      footer={
        <div className="flex flex-col gap-3">
          {saveError && (
            <ConfigPanelErrorCallout message={t("memory.saveError")} />
          )}
          <PanelFooterActions align="between">
            <Button onClick={onClose}>{t("common.cancel")}</Button>
            <span className="panel-footer-actions__spacer" />
            <Button
              variant="primary"
              onClick={handleSave}
              disabled={saving || loadingContent || loadError}
              loading={saving}
              leftIcon={<Save size={14} />}
            >
              {saving
                ? t("memory.saving")
                : saveError
                  ? t("common.retry")
                  : t("common.save")}
            </Button>
          </PanelFooterActions>
        </div>
      }
    >
      <fieldset disabled={saving} className="es-form min-w-0">
        {memory?.updated_at && (
          <p className="es-hint">{relativeTime(memory.updated_at)}</p>
        )}
        <div className="es-section">
          <FormField
            label={t("memory.titleLabel")}
            htmlFor={`${formId}-title`}
            className="es-field"
          >
            <Input
              id={`${formId}-title`}
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={t("memory.titlePlaceholder")}
              className="es-input"
              maxLength={80}
            />
          </FormField>

          <FormField
            label={t("memory.summaryLabel")}
            htmlFor={`${formId}-summary`}
            className="es-field"
          >
            <Input
              id={`${formId}-summary`}
              type="text"
              value={summary}
              disabled={loadingContent || loadError || saving}
              onChange={(e) => setSummary(e.target.value)}
              placeholder={t("memory.summaryPlaceholder")}
              className="es-input"
              maxLength={300}
            />
          </FormField>
        </div>

        <div className="es-section">
          <div className="es-field">
            <label className="es-label">{t("memory.typeLabel")}</label>
            <div className="flex flex-wrap gap-2">
              {TYPE_OPTIONS_LIST.map((opt) => {
                const selected = memoryType === opt.value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    aria-pressed={selected}
                    onClick={() => setMemoryType(opt.value)}
                    className={`inline-flex min-h-11 sm:min-h-0 items-center gap-1 rounded-full border px-2 py-1 text-11 font-medium transition-all ${
                      selected
                        ? `${
                            TYPE_STYLES[opt.value]
                          } border-transparent shadow-sm ring-1 ring-[var(--theme-primary)]`
                        : "border-[var(--glass-border)] bg-[var(--glass-bg-subtle)] text-[var(--theme-text-secondary)] hover:bg-[var(--glass-bg-hover)]"
                    }`}
                  >
                    <span
                      className={`h-1.5 w-1.5 rounded-full ${
                        TYPE_DOTS[opt.value]
                      }`}
                    />
                    {t(opt.labelKey)}
                  </button>
                );
              })}
            </div>
          </div>

          {isEdit && (
            <div className="es-field">
              <label className="es-label">{t("memory.sourceLabel")}</label>
              <div className="flex flex-wrap gap-2">
                {SOURCE_OPTIONS_LIST.map((opt) => {
                  const selected = source === opt.value;
                  return (
                    <button
                      key={opt.value}
                      type="button"
                      aria-pressed={selected}
                      onClick={() => setSource(opt.value)}
                      className={`inline-flex min-h-11 sm:min-h-0 items-center gap-1 rounded-full border px-2 py-1 text-11 font-medium transition-all ${
                        selected
                          ? `${
                              SOURCE_STYLES[opt.value]
                            } border-transparent shadow-sm ring-1 ring-[var(--theme-primary)]`
                          : "border-[var(--glass-border)] bg-[var(--glass-bg-subtle)] text-[var(--theme-text-secondary)] hover:bg-[var(--glass-bg-hover)]"
                      }`}
                    >
                      <span
                        className={`h-1.5 w-1.5 rounded-full ${
                          SOURCE_DOTS[opt.value]
                        }`}
                      />
                      {t(opt.labelKey)}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        <div
          ref={contentRef}
          tabIndex={-1}
          className="es-section focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)]"
        >
          <label htmlFor={`${formId}-content`} className="es-label">
            {t("memory.contentLabel")}
          </label>
          {loadingContent ? (
            <div
              role="status"
              className="flex min-h-48 items-center justify-center"
            >
              <Loading text={t("common.loading")} size="sm" />
            </div>
          ) : loadError ? (
            <>
              <ConfigPanelErrorCallout message={t("common.loadFailed")} />
              <Button
                size="lg"
                className="self-start"
                onClick={() => {
                  contentRef.current?.focus();
                  retry();
                }}
              >
                {t("common.retry")}
              </Button>
            </>
          ) : (
            <Textarea
              id={`${formId}-content`}
              value={content}
              disabled={saving}
              onChange={(e) => setContent(e.target.value)}
              placeholder={t("memory.contentPlaceholder")}
              className="es-textarea min-h-48"
              rows={8}
            />
          )}
        </div>

        <FormField
          label={t("memory.tagsLabel")}
          htmlFor={`${formId}-tags`}
          className="es-section es-field"
        >
          <Input
            id={`${formId}-tags`}
            type="text"
            value={tagsInput}
            onChange={(e) => setTagsInput(e.target.value)}
            placeholder={t("memory.tagsPlaceholder")}
            className="es-input"
          />
          {tagsInput.trim() && (
            <div className="flex flex-wrap gap-1.5">
              {tagsInput
                .split(/[,，]/)
                .map((tag) => tag.trim())
                .filter(Boolean)
                .slice(0, 8)
                .map((tag) => (
                  <span key={tag} className="es-chip">
                    {tag}
                  </span>
                ))}
            </div>
          )}
        </FormField>
      </fieldset>
    </EditorSidebar>
  );
}
