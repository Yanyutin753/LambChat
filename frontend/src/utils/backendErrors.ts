import type { TFunction } from "i18next";

const BACKEND_ERROR_KEYS: Record<string, string> = {
  // Stable backend error codes
  persona_preset_not_found: "personaPresets.presetNotFound",
  persona_preset_no_edit_permission: "personaPresets.noEditPermission",
  persona_preset_no_delete_permission: "personaPresets.noDeletePermission",
  persona_preset_no_admin_permission: "personaPresets.noAdminPermission",
  model_not_found: "errors.modelNotFound",
  model_disabled: "errors.modelDisabled",
  model_not_allowed: "errors.modelNotAllowed",
  invalid_attachments: "backendErrors.invalidAttachments",

  // Stable HTTPException detail strings
  未提供认证信息: "backendErrors.authMissing",
  "无效的 Token": "backendErrors.invalidToken",
  用户不存在: "backendErrors.userNotFound",
  未认证的用户: "backendErrors.unauthenticated",
  无权访问此会话: "backendErrors.sessionAccessDenied",
  会话不存在: "backendErrors.sessionNotFound",
  删除失败: "backendErrors.deleteFailed",
  更新失败: "backendErrors.updateFailed",
  收藏状态更新失败: "backendErrors.favoriteUpdateFailed",
  项目不存在: "backendErrors.projectNotFound",
  移动失败: "backendErrors.moveFailed",
  移动后收藏状态同步失败: "backendErrors.moveFavoriteSyncFailed",
  角色不存在: "backendErrors.roleNotFound",
  不能修改自己所属角色的权限: "backendErrors.cannotChangeOwnRolePermissions",
  审批请求不存在: "backendErrors.approvalNotFound",
  审批请求已处理: "backendErrors.approvalAlreadyHandled",
  角色预设不存在: "personaPresets.presetNotFound",
  不能创建收藏项目: "backendErrors.cannotCreateFavoritesProject",
  不能删除收藏项目: "backendErrors.cannotDeleteFavoritesProject",
  没有分享会话的权限: "backendErrors.shareNoPermission",
  只能分享自己的会话: "backendErrors.shareOwnOnly",
  "部分分享需要指定 run_ids": "backendErrors.sharePartialNeedsRunIds",
  只能查看自己会话的分享: "backendErrors.shareViewOwnOnly",
  分享不存在: "backendErrors.shareNotFound",
  只能删除自己创建的分享: "backendErrors.shareDeleteOwnOnly",
  分享不存在或已过期: "backendErrors.shareExpiredOrMissing",
  需要登录才能查看此分享: "backendErrors.shareLoginRequired",
  原会话已不存在: "backendErrors.shareSourceMissing",
  注册已关闭: "backendErrors.registrationClosed",
  人机验证失败请重试: "backendErrors.turnstileFailed",
  "人机验证失败，请重试": "backendErrors.turnstileFailed",
  用户名或密码错误: "backendErrors.invalidCredentials",
  请先验证邮箱后再登录: "backendErrors.emailVerificationRequired",
  账户未激活请验证邮箱后登录: "backendErrors.accountInactive",
  "账户未激活，请验证邮箱后登录": "backendErrors.accountInactive",
  缺少刷新令牌: "backendErrors.refreshTokenMissing",
  无效的刷新令牌: "backendErrors.refreshTokenInvalid",
  无效的令牌内容: "backendErrors.invalidTokenPayload",
  请求过于频繁请稍后再试: "backendErrors.tooManyRequests",
  "请求过于频繁，请稍后再试": "backendErrors.tooManyRequests",
  该邮箱请求过于频繁请稍后再试: "backendErrors.emailTooManyRequests",
  "该邮箱请求过于频繁，请稍后再试": "backendErrors.emailTooManyRequests",
  邮件服务未启用: "backendErrors.emailServiceDisabled",
  无效的重置令牌: "backendErrors.invalidResetToken",
  重置令牌已过期: "backendErrors.resetTokenExpired",
  无效或过期的验证令牌: "backendErrors.invalidVerificationToken",
  状态必须是active或archived: "backendErrors.invalidSessionStatus",
  "状态必须是 active 或 archived": "backendErrors.invalidSessionStatus",

  "Channel instance not found": "backendErrors.channelInstanceNotFound",
  "Channel instance is disabled": "backendErrors.channelInstanceDisabled",
  "Instance name is required": "backendErrors.instanceNameRequired",
  "Invalid key format. Must match: ^[A-Za-z_][A-Za-z0-9_]*$":
    "backendErrors.invalidEnvKeyFormat",
  "Invalid file ID format": "backendErrors.invalidFileId",
  "File must be a ZIP archive": "backendErrors.zipRequired",
  "Failed to read file content": "backendErrors.fileReadFailed",
  "Invalid file path": "backendErrors.invalidFilePath",
  "File not found": "backendErrors.fileNotFound",
  "Empty file": "backendErrors.emptyFile",
  "User not found": "backendErrors.userNotFound",
  "Marketplace skill name is required":
    "backendErrors.marketplaceSkillNameRequired",
  "Skill must have at least one file": "backendErrors.skillFileRequired",
  "Failed to sync files, marketplace entry rolled back":
    "backendErrors.marketplaceSyncRolledBack",
  "Failed to sync files to marketplace": "backendErrors.marketplaceSyncFailed",
  "Failed to publish skill": "backendErrors.publishSkillFailed",
  "Only creator can update": "backendErrors.onlyCreatorCanUpdate",
  "This skill has been deactivated": "backendErrors.skillDeactivated",
  "Marketplace skill has no files": "backendErrors.marketplaceSkillNoFiles",
  "Skill not found": "backendErrors.skillNotFound",
  "Setting not found": "backendErrors.settingNotFound",
  "Notification not found": "backendErrors.notificationNotFound",
  "Memory backend not available": "backendErrors.memoryBackendUnavailable",
  "Memory not found": "backendErrors.memoryNotFound",
  "memory_ids must be a non-empty list": "backendErrors.memoryIdsRequired",
  "Cannot delete more than 100 memories at once":
    "backendErrors.memoryDeleteLimit",
  "Repository or branch not found": "backendErrors.repositoryOrBranchNotFound",
  "No skills found in repository": "backendErrors.noSkillsFoundInRepository",
  "Only the creator can toggle tools on this server":
    "backendErrors.onlyCreatorCanToggleTools",
  "target_user_id is required to identify the user server":
    "backendErrors.targetUserRequired",
  "target_user_id is required to specify the new owner":
    "backendErrors.targetOwnerRequired",
  "Upload failed: duplicate record conflict":
    "backendErrors.uploadDuplicateConflict",
  "Avatar file size exceeds maximum of 2MB": "backendErrors.avatarTooLarge",
  "expires must be between 60 and 86400 seconds":
    "backendErrors.invalidExpiresRange",
  "Failed to read file": "backendErrors.fileReadFailed",
  "Failed to generate file URL": "backendErrors.fileUrlFailed",
  "Failed to create authorization URL": "backendErrors.oauthUrlFailed",
  "Invalid OAuth state. Please try logging in again.":
    "backendErrors.oauthStateInvalid",
  "OAuth authentication failed": "backendErrors.oauthFailed",
  "Invalid disabled_tools: must be a list of strings.":
    "backendErrors.invalidDisabledTools",
  "Invalid pinned_model_ids: must be a list of strings.":
    "backendErrors.invalidPinnedModelIds",
  "Too many pinned models: maximum 10 allowed.":
    "backendErrors.tooManyPinnedModels",
  "models must be a non-empty list": "backendErrors.modelsRequired",
  "A model cannot be its own fallback": "backendErrors.modelFallbackSelf",
};

const BACKEND_ERROR_PATTERNS: Array<{
  pattern: RegExp;
  key: string;
  values?: (match: RegExpMatchArray) => Record<string, string>;
}> = [
  {
    pattern: /^缺少权限: (.+)$/,
    key: "backendErrors.permissionMissing",
    values: (match) => ({ permission: match[1] }),
  },
  {
    pattern: /^No permission to upload (.+) files$/,
    key: "backendErrors.fileUploadNoPermission",
    values: (match) => ({ category: match[1] }),
  },
  {
    pattern: /^File size exceeds maximum of (.+)MB$/,
    key: "backendErrors.fileTooLarge",
    values: (match) => ({ max: match[1] }),
  },
];

export function translateBackendError(message: string, t: TFunction): string {
  const key = BACKEND_ERROR_KEYS[message];
  if (key) return t(key, key);

  for (const entry of BACKEND_ERROR_PATTERNS) {
    const match = message.match(entry.pattern);
    if (match) {
      return t(entry.key, {
        defaultValue: entry.key,
        ...(entry.values ? entry.values(match) : {}),
      });
    }
  }

  return message;
}
