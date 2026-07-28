import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  getSendShortcutDisplay,
  readSendModifier,
} from "../../hooks/sendModifier";

export function ShortcutRow({
  label,
  keys,
  macKeys,
}: {
  label: string;
  keys: string[];
  macKeys?: string[];
}) {
  const isMac =
    typeof navigator !== "undefined" &&
    navigator.platform.toUpperCase().indexOf("MAC") >= 0;
  const displayKeys = isMac && macKeys ? macKeys : keys;
  return (
    <div className="flex items-center justify-between gap-4">
      <span>{label}</span>
      <div className="flex gap-1">
        {displayKeys.map((key) => (
          <kbd
            key={key}
            className="px-1.5 py-0.5 rounded text-[11px] font-mono"
            style={{
              backgroundColor: "var(--theme-bg-hover, rgba(128,128,128,0.1))",
              border: "1px solid var(--theme-border)",
              color: "var(--theme-text-secondary)",
            }}
          >
            {key}
          </kbd>
        ))}
      </div>
    </div>
  );
}

export function ShortcutDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { t } = useTranslation();

  if (!open) return null;

  return (
    <div
      className="safe-area-viewport-padding fixed inset-0 z-[100] flex items-center justify-center"
      onClick={onClose}
    >
      <div
        className="absolute inset-0"
        style={{ backgroundColor: "rgba(0,0,0,0.4)" }}
      />
      <div
        className="relative w-full max-w-md mx-4 rounded-2xl p-5 shadow-xl"
        style={{
          backgroundColor: "var(--theme-bg-card)",
          border: "1px solid var(--theme-border)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h3
            className="text-base font-semibold"
            style={{ color: "var(--theme-text)" }}
          >
            {t("chat.keyboardShortcuts", "键盘快捷键")}
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-lg transition-colors cursor-pointer"
            style={{ color: "var(--theme-text-secondary)" }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor =
                "var(--theme-bg-hover, rgba(128,128,128,0.08))";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = "transparent";
            }}
          >
            <X size={16} />
          </button>
        </div>
        <div
          className="space-y-3 text-[13px]"
          style={{ color: "var(--theme-text-secondary)" }}
        >
          <div
            className="pb-2 mb-1 text-[11px] font-medium uppercase tracking-wider"
            style={{
              color: "var(--theme-text-secondary)",
              opacity: 0.5,
            }}
          >
            {t("shortcut.categoryChat", "对话")}
          </div>
          <ShortcutRow
            label={t("shortcut.send", "发送消息")}
            {...getSendShortcutDisplay(readSendModifier())}
          />
          <ShortcutRow label={t("shortcut.newline", "换行")} keys={["Enter"]} />
          <ShortcutRow
            label={t("shortcut.historyUp", "上一条历史")}
            keys={["↑"]}
          />
          <ShortcutRow
            label={t("shortcut.historyDown", "下一条历史")}
            keys={["↓"]}
          />
          <div
            className="pt-2 pb-2 mt-1 text-[11px] font-medium uppercase tracking-wider"
            style={{
              color: "var(--theme-text-secondary)",
              opacity: 0.5,
            }}
          >
            {t("shortcut.categoryGeneral", "通用")}
          </div>
          <ShortcutRow
            label={t("shortcut.newChat", "新建对话")}
            keys={["Ctrl", "N"]}
            macKeys={["⌘", "N"]}
          />
          <ShortcutRow
            label={t("shortcut.newChatAlt", "新建对话 (备选)")}
            keys={["Ctrl", "Shift", "O"]}
            macKeys={["⌘", "Shift", "O"]}
          />
          <ShortcutRow
            label={t("shortcut.search", "搜索对话")}
            keys={["Ctrl", "K"]}
            macKeys={["⌘", "K"]}
          />
          <ShortcutRow
            label={t("shortcut.selectPersona", "选择角色")}
            keys={["@"]}
          />
          <ShortcutRow
            label={t("shortcut.selectTeam", "选择团队")}
            keys={["Ctrl", "T"]}
            macKeys={["⌘", "T"]}
          />
          <div
            className="pt-2 pb-2 mt-1 text-[11px] font-medium uppercase tracking-wider"
            style={{
              color: "var(--theme-text-secondary)",
              opacity: 0.5,
            }}
          >
            {t("shortcut.categoryDialog", "弹窗")}
          </div>
          <ShortcutRow
            label={t("shortcut.closeDialog", "关闭弹窗")}
            keys={["Esc"]}
          />
          <ShortcutRow
            label={t("shortcut.confirm", "确认提交")}
            keys={["Ctrl", "Enter"]}
            macKeys={["⌘", "Enter"]}
          />
          <ShortcutRow
            label={t("shortcut.goal", "设置目标")}
            keys={["/", "goal"]}
          />
        </div>
      </div>
    </div>
  );
}
