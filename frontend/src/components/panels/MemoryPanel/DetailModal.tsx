import { useRef } from "react";
import { useTranslation } from "react-i18next";
import { Eye, Trash2, Pencil, Clock, Tag } from "lucide-react";
import { EditorSidebar } from "../../common/EditorSidebar";
import { Button, PanelFooterActions } from "../../common";
import type { MemoryItem } from "../../../services/api/memory";
import { Loading } from "../../common/LoadingSpinner";
import { ConfigPanelErrorCallout } from "../ConfigPanelErrorCallout";
import { useMemoryContent } from "./useMemoryContent";
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
  const { full, loading, error, retry } = useMemoryContent(memory);
  const contentRef = useRef<HTMLDivElement>(null);

  const style = TYPE_STYLES[memory.memory_type] ?? TYPE_STYLES.user;

  return (
    <EditorSidebar
      open={true}
      onClose={onClose}
      title={memory.title}
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
        <div className="flex min-w-0 flex-col gap-3">
          {/* Type badge & time */}
          <div className="flex flex-wrap items-center gap-2">
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
            <p className="es-hint flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="inline-flex items-center gap-1">
                <Clock size={12} className="shrink-0" />
                {formatDateTime(memory.created_at)}
              </span>
              <span>
                {memory.access_count ?? 0} {t("memory.accesses")}
              </span>
            </p>
          )}

          {/* Tags */}
          {memory.tags.length > 0 && (
            <div className="flex items-center gap-1.5 flex-wrap">
              <Tag
                size={12}
                className="text-theme-text-secondary flex-shrink-0"
              />
              {memory.tags.slice(0, 8).map((tag) => (
                <span
                  key={tag}
                  className="es-chip max-w-full [overflow-wrap:anywhere]"
                >
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Divider */}
        <hr className="es-divider" />

        {/* Content */}
        <div
          ref={contentRef}
          tabIndex={-1}
          className="min-w-0 flex flex-col gap-3 focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)]"
        >
          {loading ? (
            <div
              role="status"
              className="flex items-center justify-center py-12"
            >
              <Loading text={t("common.loading")} size="sm" />
            </div>
          ) : error ? (
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
            <p className="text-14 text-theme-text whitespace-pre-wrap leading-relaxed [overflow-wrap:anywhere]">
              {full?.content || full?.summary}
            </p>
          )}
        </div>
      </div>
    </EditorSidebar>
  );
}
