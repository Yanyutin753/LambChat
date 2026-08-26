/**
 * 输入框 placeholder 的选择逻辑（纯函数，返回 i18n key）。
 *
 * 运行中发送会进入 steer 排队、按序生效，此时 placeholder 提示
 * 「继续输入以排队有序修改」；团队提及编辑中保持团队提示不被覆盖。
 */

export function resolveComposerPlaceholder(input: {
  canSend: boolean;
  mentionMode: "persona" | "team";
  isLoading: boolean;
}): string {
  if (!input.canSend) return "chat.noPermission";
  if (input.mentionMode === "team") return "chat.teamPlaceholder";
  if (input.isLoading) return "chat.runningPlaceholder";
  return "chat.placeholder";
}
