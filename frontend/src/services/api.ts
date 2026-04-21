/**
 * API service for backend communication
 * 支持JWT认证的API服务
 *
 * 此文件作为统一导出入口，所有 API 模块拆分在 ./api/ 目录下
 */

// Config
export { API_BASE, getFullUrl } from "./api/config";

// Token management
export {
  getAccessToken,
  getRefreshToken,
  setTokens,
  clearTokens,
  isAuthenticated,
  decodeToken,
  isTokenExpired,
  getRedirectPath,
  clearRedirectPath,
} from "./api/token";

// Auth fetch
export { authFetch } from "./api/fetch";

// API modules
export { authApi } from "./api/auth";
export { userApi } from "./api/user";
export { roleApi } from "./api/role";
export {
  sessionApi,
  type BackendSession,
  type SessionListResponse,
} from "./api/session";
export { agentApi } from "./api/agent";
export { agentConfigApi } from "./api/agent_config";
export { modelApi } from "./api/model";
export { skillApi } from "./api/skill";
export { settingsApi } from "./api/settings";
export { mcpApi } from "./api/mcp";
export { memoryApi } from "./api/memory";
export { envvarApi } from "./api/envvar";
export { uploadApi } from "./api/upload";
export { versionApi } from "./api/version";
export { projectApi } from "./api/project";
export {
  revealedFileApi,
  type RevealedFileItem,
  type RevealedFileListParams,
  type RevealedFileGroupedListParams,
  type RevealedFileGroupedListResponse,
  type SessionGroupItem,
} from "./api/revealedFile";
