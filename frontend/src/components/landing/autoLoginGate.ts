export interface AutoLoginGateState {
  isLoading: boolean;
  isAuthenticated: boolean;
  hasToken: boolean;
}

/**
 * `/` 上已持有 token 且鉴权仍在校验时，几乎必然会被自动带进 `/chat`——
 * 此时先显示品牌过渡页，而不是渲染整个营销落地页再被跳走（落地页闪现）。
 */
export function shouldShowAutoLoginSplash({
  isLoading,
  isAuthenticated,
  hasToken,
}: AutoLoginGateState): boolean {
  return isLoading && !isAuthenticated && hasToken;
}
