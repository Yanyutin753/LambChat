/** 状态提示优先于环境，避免运行中的团队仍显示开始任务的提示。 */
export function resolveComposerPlaceholder(input: {
  canSend: boolean;
  mentionMode: "persona" | "team";
  isLoading: boolean;
  sendBlocked?: boolean;
  sandbox?: boolean | string | number;
}): string {
  if (!input.canSend) return "chat.noPermission";
  if (input.sendBlocked) return "chat.replyRequiredPlaceholder";
  if (input.isLoading) return "chat.runningPlaceholder";
  if (input.mentionMode === "team") return "chat.teamPlaceholder";
  if (input.sandbox === "local") return "chat.localPlaceholder";
  if (input.sandbox === "cloud") return "chat.cloudPlaceholder";
  return "chat.placeholder";
}
