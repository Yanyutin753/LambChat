/**
 * 输入框 placeholder 的选择逻辑（纯函数，返回 i18n key）。
 *
 * 团队提及优先，其余状态使用简洁输入提示。
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
