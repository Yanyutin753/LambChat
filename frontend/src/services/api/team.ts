import { authFetch } from "./fetch";
import { API_BASE } from "./config";
import { getAccessToken } from "./token";
import { subscribeTeamsChanged } from "../../hooks/teamEvents";
import type {
  Team,
  TeamCreateRequest,
  TeamListParams,
  TeamPreferenceUpdate,
  TeamUpdateRequest,
  TeamListResponse,
} from "../../types/team";

const BASE = `${API_BASE}/api/teams`;
const TEAM_LIST_CACHE_TTL_MS = 10_000;

interface TeamListCacheEntry {
  data?: TeamListResponse;
  expiresAt: number;
  authScope: string | null;
  promise?: Promise<TeamListResponse>;
}

const teamListCache = new Map<string, TeamListCacheEntry>();

function clearTeamListCache(): void {
  teamListCache.clear();
}

function getCachedTeamList(url: string): Promise<TeamListResponse> {
  const now = Date.now();
  const authScope = getAccessToken();
  const cached = teamListCache.get(url);

  if (
    cached?.data &&
    cached.expiresAt > now &&
    cached.authScope === authScope
  ) {
    return Promise.resolve(cached.data);
  }

  if (cached?.promise && cached.authScope === authScope) {
    return cached.promise;
  }

  const promise = authFetch<TeamListResponse>(url)
    .then((data) => {
      teamListCache.set(url, {
        data,
        expiresAt: Date.now() + TEAM_LIST_CACHE_TTL_MS,
        authScope,
      });
      return data;
    })
    .catch((error) => {
      teamListCache.delete(url);
      throw error;
    });

  teamListCache.set(url, {
    promise,
    expiresAt: now + TEAM_LIST_CACHE_TTL_MS,
    authScope,
  });

  return promise;
}

export function buildTeamCollectionUrl(params?: TeamListParams): string;
export function buildTeamCollectionUrl(skip?: number, limit?: number): string;
export function buildTeamCollectionUrl(
  skipOrParams?: number | TeamListParams,
  limit?: number,
): string {
  const params =
    typeof skipOrParams === "object"
      ? skipOrParams
      : { skip: skipOrParams, limit };
  const searchParams = new URLSearchParams();
  if (params.skip !== undefined) searchParams.set("skip", String(params.skip));
  if (params.limit !== undefined)
    searchParams.set("limit", String(params.limit));
  if (params.q) searchParams.set("q", params.q);
  if (params.tag) searchParams.set("tag", params.tag);
  if (params.favorite !== undefined)
    searchParams.set("favorite", String(params.favorite));
  if (params.pinned !== undefined)
    searchParams.set("pinned", String(params.pinned));
  const query = searchParams.toString();
  return `${BASE}/${query ? `?${query}` : ""}`;
}

export function buildTeamItemUrl(teamId: string): string {
  return `${BASE}/${encodeURIComponent(teamId)}`;
}

export function buildTeamCloneUrl(teamId: string): string {
  return `${buildTeamItemUrl(teamId)}/clone`;
}

export function buildTeamPreferenceUrl(teamId: string): string {
  return `${buildTeamItemUrl(teamId)}/preference`;
}

export const teamApi = {
  async list(
    skipOrParams: number | TeamListParams = 0,
    limit = 20,
  ): Promise<TeamListResponse> {
    const url =
      typeof skipOrParams === "object"
        ? buildTeamCollectionUrl(skipOrParams)
        : buildTeamCollectionUrl(skipOrParams, limit);
    return getCachedTeamList(url);
  },

  async get(teamId: string): Promise<Team> {
    return authFetch<Team>(buildTeamItemUrl(teamId));
  },

  async create(data: TeamCreateRequest): Promise<Team> {
    const team = await authFetch<Team>(buildTeamCollectionUrl(), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    clearTeamListCache();
    return team;
  },

  async update(teamId: string, data: TeamUpdateRequest): Promise<Team> {
    const team = await authFetch<Team>(buildTeamItemUrl(teamId), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    clearTeamListCache();
    return team;
  },

  async delete(teamId: string): Promise<void> {
    await authFetch(buildTeamItemUrl(teamId), { method: "DELETE" });
    clearTeamListCache();
  },

  async clone(teamId: string): Promise<Team> {
    const team = await authFetch<Team>(buildTeamCloneUrl(teamId), {
      method: "POST",
    });
    clearTeamListCache();
    return team;
  },

  async updatePreference(
    teamId: string,
    data: TeamPreferenceUpdate,
  ): Promise<Team> {
    const team = await authFetch<Team>(buildTeamPreferenceUrl(teamId), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    clearTeamListCache();
    return team;
  },
};

subscribeTeamsChanged(() => {
  clearTeamListCache();
});
