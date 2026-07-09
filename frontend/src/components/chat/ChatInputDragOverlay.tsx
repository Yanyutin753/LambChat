import { UploadCloud } from "lucide-react";
import { useTranslation } from "react-i18next";

export function ChatInputDragOverlay() {
  const { t } = useTranslation();

  return (
    <div className="absolute inset-0 z-10 flex items-center justify-center rounded-3xl pointer-events-none">
      <div
        className="flex flex-col items-center gap-2 rounded-2xl px-10 py-8 transition-all"
        style={{
          backgroundColor:
            "color-mix(in srgb, var(--theme-primary) 6%, transparent)",
        }}
      >
        <UploadCloud
          size={28}
          className="animate-bounce"
          style={{
            color: "var(--theme-primary)",
            opacity: 0.7,
          }}
        />
        <span
          className="text-sm font-medium"
          style={{
            color: "var(--theme-primary)",
            opacity: 0.7,
          }}
        >
          {t("chat.dropFilesHere", "Drop files here to upload")}
        </span>
      </div>
    </div>
  );
}
