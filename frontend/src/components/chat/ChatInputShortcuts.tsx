import { DialogCloseButton } from "../common/DialogCloseButton";
import { ModalSurface } from "../common/ModalSurface";

import { CHAT_INPUT_SLASH_COMMANDS } from "./chatInputSlashCommands";

import { useTranslation } from "react-i18next";
import {
  getSendShortcutDisplay,
  readSendModifier,
} from "../../hooks/sendModifier";

export function ShortcutRow({
  label,
  keys,
  macKeys,
  description,
}: {
  label: string;
  keys: string[];
  macKeys?: string[];
  description?: string;
}) {
  const isMac =
    typeof navigator !== "undefined" &&
    navigator.platform.toUpperCase().includes("MAC");
  const displayKeys = isMac && macKeys ? macKeys : keys;
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="min-w-0">
        <span>{label}</span>
        {description && (
          <p className="mt-0.5 text-11 text-theme-text-tertiary">{description}</p>
        )}
      </div>
      <div className="flex shrink-0 flex-wrap justify-end gap-1">
        {displayKeys.map((key) => (
          <kbd
            key={key}
            className="px-1.5 py-0.5 rounded text-11 font-mono"
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

  const sendModifier = readSendModifier();

  return (
    <ModalSurface
      open={open}
      onClose={onClose}
      className="modal-size-md"
      label={t("chat.keyboardShortcuts")}
    >
      <div
        className="relative flex min-h-0 w-full max-w-md flex-col mx-4 rounded-2xl p-5 shadow-xl"
        style={{
          backgroundColor: "var(--theme-bg-card)",
          border: "1px solid var(--theme-border)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex shrink-0 items-center justify-between mb-4">
          <h3
            className="text-16 font-semibold"
            style={{ color: "var(--theme-text)" }}
          >
            {t("chat.keyboardShortcuts", "键盘快捷键")}
          </h3>
          <DialogCloseButton onClick={onClose} />
        </div>
        <div
          className="min-h-0 space-y-3 overflow-y-auto text-13"
          tabIndex={0}
          role="region"
          aria-label={t("chat.keyboardShortcuts")}
          style={{ color: "var(--theme-text-secondary)" }}
        >
          <div
            className="pb-2 mb-1 text-11 font-medium uppercase tracking-wider"
            style={{
              color: "var(--theme-text-secondary)",
            }}
          >
            {t("shortcut.categoryChat", "对话")}
          </div>
          <ShortcutRow
            label={t("shortcut.send", "发送消息")}
            {...getSendShortcutDisplay(sendModifier)}
          />
          <ShortcutRow
            label={t("shortcut.newline", "换行")}
            keys={sendModifier === "enter" ? ["Shift", "Enter"] : ["Enter"]}
          />
          <ShortcutRow
            label={t("shortcut.historyUp", "上一条历史")}
            description={t("shortcut.historyUpHint")}
            keys={["↑"]}
          />
          <ShortcutRow
            label={t("shortcut.historyDown", "下一条历史")}
            description={t("shortcut.historyDownHint")}
            keys={["↓"]}
          />
          <ShortcutRow
            label={t("shortcut.removeReference")}
            keys={["Backspace"]}
            macKeys={["⌫"]}
          />
          <ShortcutRow
            label={t("shortcut.removeReferenceForward")}
            keys={["Delete"]}
            macKeys={["Fn", "⌫"]}
          />
          <div
            className="pt-2 pb-2 mt-1 text-11 font-medium uppercase tracking-wider"
            style={{
              color: "var(--theme-text-secondary)",
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
            description={t("shortcut.teamHint")}
            keys={["Ctrl", "T"]}
            macKeys={["⌘", "T"]}
          />
          <ShortcutRow
            label={t("shortcut.toggleSidebar")}
            keys={["Ctrl", "B"]}
            macKeys={["⌘", "B"]}
          />
          <ShortcutRow
            label={t("shortcut.settings")}
            keys={["Ctrl", ","]}
            macKeys={["⌘", ","]}
          />
          <ShortcutRow
            label={t("shortcut.cycleTheme")}
            keys={["Ctrl", "Shift", "L"]}
            macKeys={["⌘", "Shift", "L"]}
          />
          <ShortcutRow
            label={t("shortcut.back")}
            keys={["Alt", "←"]}
            macKeys={["⌘", "["]}
          />
          <ShortcutRow
            label={t("shortcut.forward")}
            keys={["Alt", "→"]}
            macKeys={["⌘", "]"]}
          />
          <p className="text-11 text-theme-text-tertiary">
            {t("shortcut.globalHint")}
          </p>
          <div
            className="pt-2 pb-2 mt-1 text-11 font-medium uppercase tracking-wider"
            style={{
              color: "var(--theme-text-secondary)",
            }}
          >
            {t("shortcut.categoryDialog", "弹窗")}
          </div>
          <ShortcutRow
            label={t("shortcut.collapseComposer")}
            keys={["Esc"]}
          />
          <ShortcutRow
            label={t("shortcut.closeDialog", "关闭弹窗")}
            keys={["Esc"]}
          />
          <ShortcutRow
            label={t("shortcut.feedbackSubmit")}
            keys={["Ctrl", "Enter"]}
            macKeys={["⌘", "Enter"]}
          />
          <h4 className="pt-3 text-11 font-medium text-theme-text-secondary">
            {t("shortcut.categoryCandidates")}
          </h4>
          <ShortcutRow
            label={t("shortcut.candidatePrevious")}
            keys={["↑"]}
          />
          <ShortcutRow
            label={t("shortcut.candidateNext")}
            keys={["↓"]}
          />
          <ShortcutRow
            label={t("shortcut.candidateConfirm")}
            keys={["Enter"]}
          />
          <ShortcutRow
            label={t("shortcut.candidateConfirmTab")}
            keys={["Tab"]}
          />
          <ShortcutRow
            label={t("shortcut.candidateDismiss")}
            keys={["Esc"]}
          />
          <h4 className="pt-3 text-11 font-medium text-theme-text-secondary">
            {t("shortcut.categoryNavigation")}
          </h4>
          <ShortcutRow
            label={t("shortcut.focusNext")}
            keys={["Tab"]}
          />
          <ShortcutRow
            label={t("shortcut.focusPrevious")}
            keys={["Shift", "Tab"]}
          />
          <ShortcutRow
            label={t("shortcut.menuPrevious")}
            keys={["↑"]}
          />
          <ShortcutRow
            label={t("shortcut.menuNext")}
            keys={["↓"]}
          />
          <ShortcutRow
            label={t("shortcut.activate")}
            keys={["Enter"]}
          />
          <ShortcutRow
            label={t("shortcut.activateButton")}
            keys={["Space"]}
          />
          <ShortcutRow
            label={t("shortcut.menuFirst")}
            keys={["Home"]}
          />
          <ShortcutRow
            label={t("shortcut.menuLast")}
            keys={["End"]}
          />
          <ShortcutRow
            label={t("shortcut.contextMenu")}
            keys={["Shift", "F10"]}
          />
          <ShortcutRow
            label={t("shortcut.renameConfirm")}
            keys={["Enter"]}
          />
          <ShortcutRow
            label={t("shortcut.renameCancel")}
            keys={["Esc"]}
          />
          <h4 className="pt-3 text-11 font-medium text-theme-text-secondary">
            {t("shortcut.categoryPreview")}
          </h4>
          <p className="text-11 text-theme-text-tertiary">
            {t("shortcut.previewHint")}
          </p>
          <ShortcutRow
            label={t("shortcut.previousImage")}
            keys={["←"]}
          />
          <ShortcutRow
            label={t("shortcut.nextImage")}
            keys={["→"]}
          />
          <ShortcutRow
            label={t("shortcut.previousTab")}
            keys={["←"]}
          />
          <ShortcutRow
            label={t("shortcut.nextTab")}
            keys={["→"]}
          />
          <ShortcutRow
            label={t("shortcut.firstTab")}
            keys={["Home"]}
          />
          <ShortcutRow
            label={t("shortcut.lastTab")}
            keys={["End"]}
          />
          <ShortcutRow
            label={t("shortcut.closeTab")}
            keys={["Delete"]}
            macKeys={["Fn", "⌫"]}
          />
          <ShortcutRow
            label={t("shortcut.narrowSidebar")}
            keys={["←"]}
          />
          <ShortcutRow
            label={t("shortcut.widenSidebar")}
            keys={["→"]}
          />
          <ShortcutRow
            label={t("shortcut.diagramZoom")}
            keys={["Ctrl", "Wheel"]}
            macKeys={["⌘", "Wheel"]}
          />
          <h4 className="pt-3 text-11 font-medium text-theme-text-secondary">
            {t("shortcut.categoryEditor")}
          </h4>
          <p className="text-11 text-theme-text-tertiary">
            {t("shortcut.editorHint")}
          </p>
          <ShortcutRow
            label={t("shortcut.editorFind")}
            keys={["Ctrl", "F"]}
            macKeys={["⌘", "F"]}
          />
          <ShortcutRow
            label={t("shortcut.editorNextMatch")}
            keys={["Ctrl", "G"]}
            macKeys={["⌘", "G"]}
          />
          <ShortcutRow
            label={t("shortcut.editorPreviousMatch")}
            keys={["Ctrl", "Shift", "G"]}
            macKeys={["⌘", "Shift", "G"]}
          />
          <ShortcutRow
            label={t("shortcut.editorNextMatchF3")}
            keys={["F3"]}
          />
          <ShortcutRow
            label={t("shortcut.editorPreviousMatchF3")}
            keys={["Shift", "F3"]}
          />
          <ShortcutRow
            label={t("shortcut.editorGoToLine")}
            keys={["Ctrl", "Alt", "G"]}
            macKeys={["⌘", "Option", "G"]}
          />
          <ShortcutRow
            label={t("shortcut.editorSelectNext")}
            keys={["Ctrl", "D"]}
            macKeys={["⌘", "D"]}
          />
          <ShortcutRow
            label={t("shortcut.editorSelectAllMatches")}
            keys={["Ctrl", "Shift", "L"]}
            macKeys={["⌘", "Shift", "L"]}
          />
          <ShortcutRow
            label={t("shortcut.undo")}
            keys={["Ctrl", "Z"]}
            macKeys={["⌘", "Z"]}
          />
          <ShortcutRow
            label={t("shortcut.redo")}
            keys={["Ctrl", "Y"]}
            macKeys={["⌘", "Shift", "Z"]}
          />
          <ShortcutRow
            label={t("shortcut.editorCloseSearch")}
            keys={["Esc"]}
          />
          <h4 className="pt-3 text-11 font-medium text-theme-text-secondary">
            {t("shortcut.categoryCommands")}
          </h4>
          <p className="text-11 text-theme-text-tertiary">
            {t("shortcut.commandsHint")}
          </p>
          {CHAT_INPUT_SLASH_COMMANDS.map((command) => (
            <ShortcutRow
              key={command.id}
              label={t(command.labelKey)}
              keys={[command.command]}
            />
          ))}
          <ShortcutRow
            label={t("shortcut.selectSkill")}
            keys={["/"]}
          />
        </div>
      </div>
    </ModalSurface>
  );
}
