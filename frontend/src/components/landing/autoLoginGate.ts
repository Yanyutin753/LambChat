export interface AutoLoginGateState {
  isLoading: boolean;
  isAuthenticated: boolean;
  hasToken: boolean;
}

/**
 * 鉴权校验和已登录后的跳转都保持品牌过渡页，避免跳转 effect
 * 执行前渲染营销落地页；校验失败后仍正常展示落地页。
 */
export function shouldShowAutoLoginSplash({
  isLoading,
  isAuthenticated,
  hasToken,
}: AutoLoginGateState): boolean {
  return isAuthenticated || (isLoading && hasToken);
}
