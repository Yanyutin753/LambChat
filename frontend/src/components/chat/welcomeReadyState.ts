export interface WelcomeReadinessState {
  settingsLoading: boolean;
  currentAgent?: string;
  personaPresetsLoading: boolean;
  /** 首次列表请求是否已落地；后台刷新（搜索/换页）不应回退骨架屏（issue #158） */
  personaPresetsLoaded?: boolean;
  teamRequestSettled: boolean;
}

export function isWelcomeContentReady({
  settingsLoading,
  currentAgent,
  personaPresetsLoading,
  personaPresetsLoaded = false,
  teamRequestSettled,
}: WelcomeReadinessState) {
  const personaReady = !personaPresetsLoading || personaPresetsLoaded;
  return (
    !settingsLoading &&
    !!currentAgent &&
    (currentAgent === "team" ? teamRequestSettled : personaReady)
  );
}

export interface TeamRequestState<T> {
  requestId: number;
  cards: T[];
  isLoading: boolean;
  isSettled: boolean;
}

export function beginTeamRequest<T>(
  _state: TeamRequestState<T>,
  requestId: number,
): TeamRequestState<T> {
  return { requestId, cards: [], isLoading: true, isSettled: false };
}

export function settleTeamRequestSuccess<T>(
  state: TeamRequestState<T>,
  requestId: number,
  cards: T[],
): TeamRequestState<T> {
  if (state.requestId !== requestId) return state;
  return { requestId, cards, isLoading: false, isSettled: true };
}

export function settleTeamRequestFailure<T>(
  state: TeamRequestState<T>,
  requestId: number,
): TeamRequestState<T> {
  if (state.requestId !== requestId) return state;
  return { requestId, cards: [], isLoading: false, isSettled: true };
}
