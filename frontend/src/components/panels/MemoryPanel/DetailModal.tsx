import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Eye, Trash2, Pencil, Clock, Tag } from "lucide-react";
import { EditorSidebar } from "../../common/EditorSidebar";
import { Button, PanelFooterActions } from "../../common";
import { memoryApi, type MemoryItem } from "../../../services/api/memory";
import { TYPE_STYLES, SOURCE_STYLES, SOURCE_DOTS } from "./constants";
import { formatDateTime } from "../../../utils/datetime";

export function DetailModal({
  memory,
  onClose,
  onDelete,
  onEdit,
  relativeTime,
}: {
  memory: MemoryItem;
  onClose: () => void;
  onDelete: (id: string) => void;
  onEdit: (memory: MemoryItem) => void;
  relativeTime: (dateStr: string | null) => string;
}) {
  const { t } = useTranslation();
  const [content, setContent] = useState(memory.content);
  const [loading, setLoading] = useState(memory.has_full_content);

  useEffect(() => {
    if (!memory.has_full_content) return;
    let cancelled = false;
    memoryApi
      .get(memory.memory_id)
      .then(
        (full) => {
          if (!cancelled) setContent(full.content);
        },
        () => {
          if (!cancelled) setContent(memory.content);
        },
      )
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [memory]);

  const style = TYPE_STYLES[memory.memory_type] ?? TYPE_STYLES.user;

  return (
    <EditorSidebar
      open={true}
      onClose={onClose}
      title={memory.title}
      subtitle={t(`memory.type.${memory.memory_type}`)}
      icon={<Eye size={16} />}
      footer={
        <PanelFooterActions align="between">
          <Button
            variant="danger"
            onClick={() => onDelete(memory.memory_id)}
            leftIcon={<Trash2 size={16} />}
          >
            {t("common.delete")}
          </Button>
          <span className="panel-footer-actions__spacer" />
          <Button
            onClick={() => onEdit(memory)}
            leftIcon={<Pencil size={14} />}
          >
            {t("common.edit")}
          </Button>
          <Button onClick={onClose}>{t("common.close")}</Button>
        </PanelFooterActions>
      }
    >
      <div className="es-form">
        {/* Type badge & time */}
        <div className="flex items-center gap-2 mb-3">
          <span
            className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-11 font-semibold uppercase leading-none ${style}`}
          >
            {t(`memory.type.${memory.memory_type}`)}
          </span>
          <span
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-11 font-medium ${
              SOURCE_STYLES[memory.source] ?? SOURCE_STYLES.manual
            }`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                SOURCE_DOTS[memory.source] ?? SOURCE_DOTS.manual
              }`}
            />
            {t(`memory.source.${memory.source}`, memory.source)}
          </span>
          <span className="text-11 text-theme-text-secondary">
            {relativeTime(memory.updated_at)}
          </span>
        </div>

        {/* Created at & access count */}
        {memory.created_at && (
          <p className="es-hint flex items-center gap-1">
            <Clock size={12} />
            {formatDateTime(memory.created_at)}
            <span className="ml-2">
              {memory.access_count ?? 0} {t("memory.accesses")}
            </span>
          </p>
        )}

        {/* Tags */}
        {memory.tags.length > 0 && (
          <div className="flex items-center gap-1.5 mt-3 flex-wrap">
            <Tag
              size={12}
              className="text-theme-text-secondary flex-shrink-0"
            />
            {memory.tags.slice(0, 8).map((tag) => (
              <span key={tag} className="es-chip">
                {tag}
              </span>
            ))}
          </div>
        )}

        {/* Divider */}
        <hr className="es-divider" />

        {/* Content */}
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <svg
              className="h-6 w-6 animate-spin text-theme-text-secondary"
              viewBox="0 0 24 24"
              fill="none"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
              />
            </svg>
          </div>
        ) : (
          <div className="es-section">
            <p className="text-sm text-theme-text whitespace-pre-wrap leading-relaxed">
              {content || memory.summary}
            </p>
          </div>
        )}
      </div>
    </EditorSidebar>
  );
}
